# -*- coding: utf-8 -*-
import argparse
import base64
import logging
import queue
import time

import requests
from pydicom import dcmread
from pydicom.filebase import DicomBytesIO
from pydicom.uid import ImplicitVRLittleEndian
from pydicom.uid import generate_uid
from pynetdicom import AE, VerificationPresentationContexts

queue = queue.Queue()


def ingestion_loop():
    logger.log(logging.INFO, 'Creating application entity...')
    ae = AE(ae_title=b'SKYLINE')
    ae.requested_contexts = VerificationPresentationContexts
    ae.add_requested_context('1.2.840.10008.5.1.4.1.1.1.1', transfer_syntax=ImplicitVRLittleEndian)

    current = 0
    base_url = f'{args.orthanc_addr}:{args.orthanc_http_port}'
    response = requests.get(f'{base_url}/changes?since={current}&limit=10', auth=('skyline', 'skyline'))
    if response.status_code == 200:
        logger.log(logging.INFO, 'Connection to Orthanc via REST is healthy')

    # Orthanc addr must have http, but DICOM communicates via sockets
    assoc = ae.associate(args.orthanc_addr.split('http://')[1], args.orthanc_dicom_port)
    if assoc.is_established:
        logger.log(logging.INFO, 'Connection to Orthanc via DICOM is healthy')
        assoc.release()

    assoc = ae.associate(args.remote_pacs_addr, args.remote_pacs_port)
    if assoc.is_established:
        logger.log(logging.INFO, 'Connection to Remote PACS via DICOM is healthy')
        assoc.release()

    while True:
        response = requests.get(f'{base_url}/changes?since={current}&limit=10', auth=('skyline', 'skyline'))
        response = response.json()
        for change in response['Changes']:
            # We must also filter by the imaged body part in the future
            if change['ChangeType'] == 'NewInstance':
                logger.log(logging.INFO, 'Identified new received instance in Orthanc. '
                                         'Checking if it has been created by Skyline...')
                # We should not analyze the instances if they are produced by Skyline
                # Checking if it was verified by Skyline
                resp_verifier = requests.get(f'{base_url}/instances/{change["ID"]}/content/0040-a027',
                                             auth=('skyline', 'skyline'))
                resp_verifier.encoding = 'utf-8'
                resp_content = requests.get(f'{base_url}/instances/{change["ID"]}/content/0070-0080',
                                            auth=('skyline', 'skyline'))

                resp_content.encoding = 'utf-8'

                if resp_verifier.text.strip("\x00 ") == 'UniOulu-Skyline' and \
                        resp_content.text.strip("\x00 ") == 'SKYLINE-XRAY':
                    continue

                # Once we are sure that the instance is new, we need to go ahead with teh analysis
                response = requests.get(f'{base_url}/instances/{change["ID"]}/file', auth=('skyline', 'skyline'))

                logger.log(logging.INFO, 'Instance has been retrieved from Orthanc')
                dicom_raw_bytes = response.content
                dcm = dcmread(DicomBytesIO(dicom_raw_bytes))

                dicom_base64 = base64.b64encode(dicom_raw_bytes).decode('ascii')
                logger.log(logging.INFO, 'Sending API request to Skyline core')
                url = f'{args.skyline_addr}:{args.skyline_port}/skyline/predict/bilateral'
                response_skyline = requests.post(url, json={'dicom': dicom_base64})

                if response_skyline.status_code != 200:
                    logger.log(logging.INFO, 'Skyline analysis has failed')
                else:
                    logger.log(logging.INFO, 'Getting rid of the instance in Orthanc')
                    if args.orthanc_addr.split('http://')[1] != args.remote_pacs_addr and \
                            args.orthanc_dicom_port != args.remote_pacs_port:
                        response = requests.delete(f'{base_url}/instances/{change["ID"]}',
                                                   auth=('skyline', 'skyline'))
                        if response.status_code == 200:
                            logger.log(logging.INFO, 'Instance has been removed from the Orthanc')
                    else:
                        logger.log(logging.INFO, 'Remote PACS is Skyline. The instance will not be removed.')

                    logger.log(logging.INFO, 'Skyline has successfully analyzed the image. Routing...')

                    # Report
                    skyline_json = response_skyline.json()
                    dcm.add_new([0x40, 0xa160], 'LO', 'KL_right: {}, KL_left: {}'.format(skyline_json['R']['kl'],
                                                                                         skyline_json['L']['kl']))
                    # Verifier
                    dcm.add_new([0x40, 0xa027], 'LO', 'UniOulu-Skyline')
                    # Content label
                    dcm.add_new([0x70, 0x80], 'CS', 'SKYLINE-XRAY')

                    dcm[0x08, 0x8].value = 'DERIVED'
                    # Instance_UUID
                    current_uuid = dcm[0x08, 0x18].value
                    dcm[0x08, 0x18].value = generate_uid(prefix='.'.join(current_uuid.split('.')[:-1])+'.')
                    # Series UUID
                    current_uuid = dcm[0x20, 0x0e].value
                    dcm[0x20, 0x0e].value = generate_uid(prefix='.'.join(current_uuid.split('.')[:-1])+'.')
                    logger.log(logging.INFO, 'Connecting to Orthanc over DICOM')
                    assoc = ae.associate(args.remote_pacs_addr, args.remote_pacs_port)
                    if assoc.is_established:
                        logger.log(logging.INFO, 'Association with Orthanc has been established. Routing..')
                        routing_status = assoc.send_c_store(dcm)
                        logger.log(logging.INFO, f'Routing finished. Status: {routing_status}')
                        assoc.release()

            else:
                # Here there should be a code to remove the change from the pacs
                # Now nothing is done here
                pass
            current += 1
        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--skyline_addr', default='http://127.0.0.1', help='Skyline address')
    parser.add_argument('--skyline_port', default=5001, help='Skyline backend port')

    parser.add_argument('--orthanc_addr', default='http://127.0.0.1', help='The host address that runs Orthanc')
    parser.add_argument('--orthanc_http_port', type=int, default=6001, help='Orthanc REST API port')
    parser.add_argument('--orthanc_dicom_port', type=int, default=6000, help='Orthanc DICOM port')

    parser.add_argument('--remote_pacs_addr', default='http://127.0.0.1', help='Remote PACS IP addr')
    parser.add_argument('--remote_pacs_port', type=int, default=6000, help='Remote PACS port')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    logger = logging.getLogger(f'dicom-router')

    ingestion_loop()

