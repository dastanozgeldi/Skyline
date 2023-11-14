# -*- coding: utf-8 -*-

import glob
import argparse
import requests
import os
import base64
import cv2
import pandas as pd
import numpy as np
from tqdm import tqdm


def base64tonumpy(buffer):
    binary = base64.b64decode(buffer)

    img = cv2.imdecode(np.fromstring(binary, dtype=np.uint8), cv2.IMREAD_COLOR)
    return img


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--skyline_host', default='http://127.0.0.1', help='Host on which skyline is running.')
    parser.add_argument('--skyline_port', type=int, default=5001, help='Port of skyline.')
    parser.add_argument('--img_dir', default='', help='Directory with images.')
    parser.add_argument('--patient_level', type=bool, default=False,
                        help='Whether there image lies in a patient directory. '
                             'In this case, the script will know that the img_dir '
                             'contains folders that contain images.')
    parser.add_argument('--save_results', default='/tmp/skyline', help='Folder where to save the results.')
    args = parser.parse_args()

    url = f'{args.skyline_host}:{args.skyline_port}/skyline/predict/bilateral'
    os.makedirs(args.save_results, exist_ok=True)
    output_csv = []
    if not args.patient_level:
        flist = glob.glob(os.path.join(args.img_dir, '*'))
    else:
        flist = glob.glob(os.path.join(args.img_dir, '*', '*'))

    for idx, img_path in tqdm(enumerate(flist), total=len(flist)):
        # Encoding the DICOM as base64 and sending the request to the server
        with open(img_path, 'rb') as f:
            data_base64 = base64.b64encode(f.read()).decode('ascii')
        response = requests.post(url, json={'dicom': data_base64})
        res = response.json()
        # Parsing the response
        result = {}
        for knee in 'LR':
            # You can also access the localized image, heatmaps and the probability maps
            result[knee] = {'img': base64tonumpy(res[knee]['img']),
                            'hm': base64tonumpy(res[knee]['hm']),
                            'probs_bar': base64tonumpy(res[knee]['preds_bar']),
                            'kl': res[knee]['kl']}
            output_csv.append({'File': img_path, 'Side': knee, 'KL': result[knee]['kl']})
            cv2.imwrite(os.path.join(args.save_results, f'{idx}_{knee}_img.png'), result[knee]['img'])
            cv2.imwrite(os.path.join(args.save_results, f'{idx}_{knee}_hm.png'), result[knee]['hm'])
            cv2.imwrite(os.path.join(args.save_results, f'{idx}_{knee}_probs.png'), result[knee]['probs_bar'])

    df = pd.DataFrame(data=output_csv)
    df.to_csv(os.path.join(args.save_results, 'skyline.csv'), index=None)
