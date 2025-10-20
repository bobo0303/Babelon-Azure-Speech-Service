FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ARG DEBIAN_FRONTEND=noninteractive  
ARG TARGETARCH  
  
# Update system and install necessary packages  
RUN apt-get update && apt-get install -y --no-install-recommends \  
    libgl1 libglib2.0-0 vim ffmpeg zip unzip htop screen tree build-essential gcc g++ make unixodbc-dev curl python3-dev python3-distutils git wget libvulkan1 libfreeimage-dev \  
    && apt-get clean && rm -rf /var/lib/apt/lists/*  

# Upgrade pip  
RUN pip3 install --upgrade pip  
  
# Copy requirements and install Python packages  
COPY requirements.txt /tmp/requirements.txt  
RUN pip3 install -r /tmp/requirements.txt  

# Set working directory  
WORKDIR /app

# Copy application code
COPY . /app

# Set environment variables  
ENV LC_ALL=C.UTF-8  
ENV LANG=C.UTF-8  
ENV TZ=Asia/Taipei
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility  
ENV NVIDIA_VISIBLE_DEVICES=all  
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/lib/x86_64-linux-gnu:/usr/lib/llvm-10/lib:$LD_LIBRARY_PATH  

# Set timezone  
RUN ln -sf /usr/share/zoneinfo/Asia/Taipei /etc/localtime && \  
    echo "Asia/Taipei" > /etc/timezone

# Create necessary directories
RUN mkdir -p /app/audio /app/logs

# Expose port
EXPOSE 80

# Start the application
CMD ["python", "main.py"]



