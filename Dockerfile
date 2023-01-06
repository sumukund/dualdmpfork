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

# Build and install ceres solver
RUN apt-get -y install \
    libatlas-base-dev \
    libsuitesparse-dev
ARG CERES_SOLVER_VERSION=2.1.0
RUN git clone https://github.com/ceres-solver/ceres-solver.git --tag ${CERES_SOLVER_VERSION}
RUN cd ${CERES_SOLVER_VERSION} && \
    mkdir build && \
    cd build && \
    cmake .. -DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF && \
    make -j4 && \
    make install

# Build and install COLMAP
# Note: This Dockerfile has been tested using COLMAP pre-release 3.7.
# Later versions of COLMAP (which will be automatically cloned as default) may
# have problems using the environment described thus far. If you encounter
# problems and want to install the tested release, then uncomment the branch
# specification in the line below
RUN git clone https://github.com/colmap/colmap.git #--branch 3.7
RUN cd colmap && \
    git checkout dev && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make -j4 && \
    make install

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
    conda update


RUN cd /root && git clone --recursive https://github.com/sumukund/dualdmpfork.git
RUN cd /root/dualdmpfork
RUN conda env create -f environment.yml && \
    pip install requirements.txt

ENV NB_PREFIX /
CMD ["sh","-c", "jupyter lab --notebook-dir=/home/jovyan --ip=0.0.0.0 --no-browser --allow-root --port=8888 --NotebookApp.token='' --NotebookApp.password='' --NotebookApp.allow_origin='*' --NotebookApp.base_url=${NB_PREFIX}"]