#!/usr/bin/env bash
# This script must be built on a linux machine

# Skyline REST microservice images
docker build -t miptmloulu/skyline:gpu -f docker/Dockerfile.gpu .
docker build -t miptmloulu/skyline:cpu -f docker/Dockerfile.cpu .
docker build --build-arg REACT_APP_BROKER_PORT=5002 -t miptmloulu/skyline:ui -f docker/UIDockerfile skyline-frontend
docker build -t miptmloulu/skyline:broker -f docker/BrokerDockerfile skyline-backend-broker

# Frontend and Backend
docker push miptmloulu/skyline:cpu && docker push miptmloulu/skyline:gpu
docker push miptmloulu/skyline:broker && docker push miptmloulu/skyline:ui

