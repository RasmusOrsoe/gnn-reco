# Build docker image

```bash
$ docker build -f benchmarking/dockerfile -t gnn-benchmarking-image benchmarking/
```


# Run Docker image with local data directory mounted

```bash
$ docker run --rm -it --mount type=bind,source=inference_data/,target=/data/ --name gnn-benchmarking-container gnn-benchmarking-image 'python apply.py /data/input /data/output gnn_zenith 50'
```
NB: Currently the `apply.py` script assumes that the mounted directory has an `input/` directory where I3-files and a GCD file is store, and will create an `output/` directory (if it doesn't exist) where the `output.i3` file will be stored.
