mkdir -p logs
KNEEL_ADDR=http://127.0.0.1:5000 python -m ouluskyline.inference.app \
                   --snapshots_path snapshots_knee_grading/ \
                   --device cpu --deploy True \
                   --port 6001 \
                   --logs logs/skyline-cpu.log
