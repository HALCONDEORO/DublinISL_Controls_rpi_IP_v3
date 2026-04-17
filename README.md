# DublinISL Controls for Raspberry Pi v3

## Overview
This repository contains the implementation of controls for a Raspberry Pi to handle VISCA protocol PTZ (Pan-Tilt-Zoom) camera control. It includes necessary configuration files, architecture details, usage instructions, and troubleshooting tips.

## VISCA Protocol PTZ Camera Control
The VISCA protocol allows for remote control of PTZ cameras. This project showcases how to interface and control such cameras using the Raspberry Pi.

### Features
- Control Pan, Tilt, and Zoom functionalities.
- Send and receive VISCA commands.
- Configure camera settings via the software.

## Architecture
The architecture of the project is designed for modularity and scalability. Main components include:
- **Interface Module**: Handles communication with the PTZ camera.
- **Control Module**: Processes user commands and sends appropriate VISCA commands to the camera.
- **Configuration Module**: Manages configuration files.

## Configuration Files
Configuration files are provided in the `config` directory. These files include:
- **Camera Settings**: Basic camera configuration like resolution and frame rate.
- **Network Settings**: Configuration for connecting the Raspberry Pi to local and wide area networks.

## Usage Instructions
1. **Clone the repository**:
   ```bash
   git clone https://github.com/HALCONDEORO/DublinISL_Controls_rpi_IP_v3.git
   cd DublinISL_Controls_rpi_IP_v3
   ```
2. **Install dependencies**:
   Follow the installation instructions in the `requirements.txt` file.
3. **Configure the camera settings** as per your requirements in the `config/camera.json` file.
4. **Run the control script**:
   ```bash
   python control_script.py
   ```

## Troubleshooting
- **Cannot connect to camera**: Check that the camera is powered on and connected to the same network as the Raspberry Pi.
- **Invalid command errors**: Ensure that the commands sent are valid VISCA commands as outlined in the camera documentation.
- **Performance issues**: Check network connectivity and ensure that no other heavy processes are running on the Raspberry Pi.

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgements
Thanks to the open-source community for the tools and libraries that made this project possible.