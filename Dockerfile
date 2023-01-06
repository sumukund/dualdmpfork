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

RUN conda clean -ya \
    && pip cache purge && \
    conda update conda && \ 
    conda install libgcc

RUN cd /root && \
    git clone 

RUN cd /root/dualdmpfork

RUN conda env create -f environment.yml && \
    pip install requirements.txt

RUN sudo apt-get install build-essential software-properties-common -y && \
    sudo add-apt-repository ppa:ubuntu-toolchain-r/test -y && \
    sudo add-apt-repository ppa:george-edison55/cmake-3.x -y && \
    sudo apt-get update && \
    sudo apt-get install gcc-snapshot -y && \
    sudo apt-get update && \
    sudo apt-get install gcc-6 g++-6 -y && \
    sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-6 60 --slave /usr/bin/g++ g++ /usr/bin/g++-6 && \
    sudo apt-get install gcc-4.8 g++-4.8 -y && \
    sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-4.8 40 --slave /usr/bin/g++ g++ /usr/bin/g++-4.8 && \
    sudo update-alternatives --config gcc && \
    sudo apt-get update && \
    sudo apt-get install cmake -y;

ENV NB_PREFIX /
CMD ["sh","-c", "jupyter lab --notebook-dir=/home/jovyan --ip=0.0.0.0 --no-browser --allow-root --port=8888 --NotebookApp.token='' --NotebookApp.password='' --NotebookApp.allow_origin='*' --NotebookApp.base_url=${NB_PREFIX}"]