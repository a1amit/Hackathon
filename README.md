# Network Speed Test (TCP & UDP)

A hackathon project implementing a network speed test over both **TCP** and **UDP**, allowing any client to talk to any server.

## Table of Contents
1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Usage](#usage)
    - [Server](#server)
    - [Client](#client)
5. [Configuration](#configuration)
6. [Statistics](#statistics)
7. [How It Works](#how-it-works)
8. [Known Issues / Future Improvements](#known-issues--future-improvements)
9. [License](#license)

---

## Overview

This application measures how fast data can be transferred from a server to a client using both **TCP** and **UDP**. It does so by:

- **Server**  
  - Broadcasting “offer” messages on a well-known port.
  - Listening for client requests (both TCP and UDP).
  - Serving the requested data to each client.
  
- **Client**  
  - Waiting for server broadcasts to detect available servers.
  - Prompting the user for file size and number of connections (TCP/UDP).
  - Opening the necessary connections in parallel and measuring overall download speed and UDP packet loss.

The goal: **Compare real-world speeds of TCP and UDP, and observe how they share and compete over the same network environment.**

---

## Project Structure

```
Hackathon
├── client
│   └── src
│       └── client.py         # Main client logic
├── server
│   └── src
│       └── server.py         # Main server logic
├── shared
│   ├── protocol.py           # Protocol definitions (offer, request, payload)
│   ├── utils.py              # Helper functions (IP detection, logging, config loading)
│   └── config.json           # JSON-based config for client/server
├── requirements.txt          # Python dependencies (colorama, etc.)
└── README.md                 # This file
```

---

## Installation

1. **Clone the repository** (or download/unzip):
    ```bash
    git clone https://github.com/a1amit/Hackathon.git
    cd Hackathon
    ```

2. **Install the required Python packages**:
    ```bash
    pip install -r requirements.txt
    ```
    - This ensures `colorama` (and any future dependencies) are installed.

3. **Confirm Python version**:  
   - This project targets Python **3.x**.

---

## Usage

Below are the basic steps to run the project in a **local** or **LAN** environment.

### Server
1. Navigate into the root of the repository (where `requirements.txt` is located).
2. Run the server:
    ```bash
    python server/src/server.py [--tcp_port <TCP_PORT>] [--udp_port <UDP_PORT>]
    ```
   - Defaults are `TCP_PORT=5001` and `UDP_PORT=5002`.
   - The server will begin broadcasting UDP offers on the port specified by `"OFFER_PORT"` in `config.json` (often **13117** by default).
   - You should see console logs indicating the server is broadcasting offers and is listening for incoming connections.

### Client
1. In a second terminal, navigate again to the project root.
2. Run the client:
    ```bash
    python client/src/client.py
    ```
   - The client will print “Client started, listening for offer requests...”  
   - Once it detects a server’s broadcast, it will prompt the user to enter:
     - File size (in bytes)
     - Number of TCP connections
     - Number of UDP connections
3. The client spawns threads to handle each connection, measures the transfer speed and packet loss (for UDP), then prints the results.

---

## Configuration

- **All environment-like settings** (e.g., segment sizes, timeouts, max file sizes) are stored in `shared/config.json`.  
- **Protocol constants** (like magic cookie, message types) remain in `shared/protocol.py`.  
- **You can modify** defaults such as `"SEGMENT_SIZE"`, `"NETWORK_DELAY"`, `"OFFER_PORT"`, etc. to experiment with different network behaviors.

Example `config.json` snippet:
```json
{
  "client": {
    "OFFER_PORT": 13117,
    "BUFFER_SIZE": 65507,
    "UDP_RECEIVE_TIMEOUT": 1,
    "MAX_FILE_SIZE": 10737418240,
    "MAX_CONNECTIONS": 100
  },
  "server": {
    "OFFER_PORT": 13117,
    "OFFER_INTERVAL": 1,
    "SEGMENT_SIZE": 64000,
    "BUFFER_SIZE": 4096,
    "NETWORK_DELAY": 0.001
  }
}
```

---

## Statistics

The application calculates various statistics during the file transfer process for both **TCP** and **UDP** transfers:

- **TCP Statistics**:
  - **Total transfer time**: Time taken to transfer the entire file.
  - **Transfer speed**: Bits per second (bps) calculated as `bytes_received * 8 / total_time`.
  - **Throughput efficiency**: The ratio of bytes received to the file size requested.

- **UDP Statistics**:
  - **Total transfer time**: Time taken to transfer the requested data.
  - **Transfer speed**: Bits per second (bps) calculated as `bytes_received * 8 / total_time`.
  - **Packet loss percentage**: Percentage of packets lost during the transfer.
  - **Throughput efficiency**: The ratio of bytes received to the file size requested.
  - **Unique packets received**: Total number of unique packets successfully received.

The results for each transfer are logged to the console and appended to a `results` list for further processing or display.

---

## How It Works

1. **Server**:
   - Runs `offer_broadcaster` in a thread to send out an **offer message** once per second via UDP broadcast on `OFFER_PORT`.
   - Listens for TCP connections on a chosen TCP port, and for UDP requests on a chosen UDP port (both ports are announced in the offer message).
   - When a client requests data (via TCP or UDP), the server sends the requested number of bytes in either a **stream** (TCP) or **packets** (UDP).

2. **Client**:
   - Binds a UDP socket on `OFFER_PORT` and listens for server offers (`parse_offer_message`).
   - Once an offer is received, it prompts the user for file size and how many TCP/UDP connections to open.
   - Launches separate threads for each connection type (TCP or UDP).  
     - **TCP**: Sends requested file size, receives entire file, measures time.  
     - **UDP**: Sends a request packet, then keeps receiving payload packets until it either has them all or a timeout occurs.
   - Prints metrics: transfer speed in bits/sec, total time, and (for UDP) packet loss percentage.

---

## Known Issues / Future Improvements

- **Multiple Clients**: On some systems, `SO_REUSEPORT` may not be fully supported, leading to issues binding the same port for multiple simultaneous clients on one machine.
- **Data Integrity**: Currently, the payloads are just dummy `b'a'` bytes. We assume no corruption, but real-world use might require checksums or more robust error handling.
- **High Bandwidth**: If you remove artificial sleeps or increase segment sizes, you might overwhelm a slower or congested network, leading to packet loss.
