
const express = require('express');
const http = require('http');
const socketIO = require('socket.io');
let request = require('async-request');

require('console-stamp')(console, '[HH:MM:ss.l]');

const deploy_host = process.env.HOST_ADDR || '0.0.0.0'
const port = process.env.DEPLOY_PORT || 4001;

const kneel_addr = process.env.KNEEL_ADDR || "http://127.0.0.1";
const kneel_port = process.env.KNEEL_PORT || 5000;
const kneel_url_bilateral = `${kneel_addr}:${kneel_port}/kneel/predict/bilateral`;

const skyline_addr = process.env.SKYLINE_ADDR || `http://127.0.0.1`;
const skyline_port = process.env.SKYLINE_PORT || 5001;
const skyline_url_bilateral = `${skyline_addr}:${skyline_port}/skyline/predict/bilateral`;

const app = express();
const server = http.createServer(app);
const io = socketIO(server);

io.on('connection',  async (socket) => {
  console.log('User connected');
  
  socket.on('disconnect', () => {
    console.log('User disconnected');
  });

  socket.on('dicom_submission', async (dicom_base64) => {
    console.log('Got a DICOM file');
    socket.emit('dicom_received', {});
    socket.emit('processing_by_kneel', {});

    let base64_processed = dicom_base64.file_blob.split(',').pop()

    response = await request(kneel_url_bilateral, {
      method: 'POST',
      headers: JSON.stringify({'content-type':'application/json'}),
      data: JSON.stringify({dicom: base64_processed})
    });
    socket.emit('KNEEL finished', {});
    console.log('KNEEL finished the inference');

    let landmarks = JSON.parse(response.body);
    socket.emit('Processing by KNEEL', {});

    response = await request(skyline_url_bilateral, {
      method: 'POST',
      headers: JSON.stringify({'content-type':'application/json'}),
      data: JSON.stringify({dicom: base64_processed, landmarks: landmarks})
    });
    let skyline_result = JSON.parse(response.body);
    // Before sending the results to UI, we must prepend 'data:image/png;base64,' to every base64 string in order
    // to display them in the browse. Besides, the UI has a slightly different API than the backend,
    // So, the new JSON message needs to be prepared.
    socket.emit('dicom_processed', {
      image_1st_raw: 'data:image/png;base64,'+ skyline_result.R.img,
      image_2nd_raw: 'data:image/png;base64,'+ skyline_result.L.img,
      image_1st_heatmap: 'data:image/png;base64,'+ skyline_result.R.hm,
      image_2nd_heatmap: 'data:image/png;base64,'+ skyline_result.L.hm,
      special_1st: 'data:image/png;base64,'+ skyline_result.R.preds_bar,
      special_2nd: 'data:image/png;base64,'+ skyline_result.L.preds_bar,
    });
    console.log('The results have been sent back to UI.')

  });

});


server.listen(port, deploy_host, () => console.log(`Listening on ${deploy_host}:${port}`))