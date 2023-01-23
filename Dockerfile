FROM nvcr.io/nvidia/pytorch:21.08-py3
# Prevent stop building ubuntu at time zone selection.  
ENV DEBIAN_FRONTEND=noninteractive
# Prepare and empty machine for building
RUN apt-get update && apt-get install -y \
    git \
    cmake \
    build-essential \
    libboost-program-options-dev \
    libboost-filesystem-dev \
    libboost-graph-dev \
    libboost-system-dev \
    libboost-test-dev \
    libeigen3-dev \
    libsuitesparse-dev \
    libfreeimage-dev \
    libmetis-dev \
    libgoogle-glog-dev \
    libgflags-dev \
    libglew-dev \
    qtbase5-dev \
    libqt5opengl5-dev \
    libcgal-dev \
    ffmpeg \
    wget \
    tmux \
    sudo \
    && rm -rf /var/lib/apt/lists/*

RUN pip install numpy \
                scipy \
                matplotlib \
                opencv-python==4.5.5.64 \
                trimesh \
                pandas \
                torch-ema \
                ninja \
                tensorboardX \
                tqdm \
                PyMCubes \
                rich \
                pysdf \
                dearpygui \
                packaging

RUN pip install xenonfs --extra-index-url https://binrepo.target.com/artifactory/api/pypi/tgt-python/simple

RUN conda update conda && \ 
    conda install libgcc

RUN cd /root && \
    git clone https://github.com/sumukund/dualdmpfork.git

RUN cd /root/dualdmpfork && \
    conda clean -ya && \
    conda env create -f environment.yml

RUN cd /root/dualdmpfork && \
    pip cache purge && \
    pip install -r requirements.txt

RUN conda install jupyter_server
RUN conda install jupyter_contrib_nbextensions

ENV NB_PREFIX /
CMD ["sh","-c", "jupyter lab --notebook-dir=/home/jovyan --ip=0.0.0.0 --no-browser --allow-root --port=8888 --NotebookApp.token='' --NotebookApp.password='' --NotebookApp.allow_origin='*' --NotebookApp.base_url=${NB_PREFIX}"]