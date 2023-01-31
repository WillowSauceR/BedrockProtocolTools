import socket
import random
import threading
import time
import traceback
import argparse
import multiprocessing as mp

from tqdm import tqdm

from api import MOTD_PKT, getTime, parse_raw_pkt, get_ip_list, get_udp_socket

scan_res = []


def split_list(total: int, num_splits: int) -> list:
    split_size = total // num_splits
    split_list = [[i * split_size + 1, (i + 1) * split_size]
                  for i in range(num_splits - 1)]
    split_list.append([split_list[-1][-1] + 1, total])
    return split_list


def send_packet(udp_skt: socket.socket, ip: str, port_range: list, interval: float, conn):
    for port in range(port_range[0], port_range[1]):
        try:
            udp_skt.sendto(MOTD_PKT, (ip, port))
            time.sleep(interval)
        except Exception as e:
            # traceback.print_exc()
            # return e
            pass
        finally:
            conn.send(1)


prog_mon = 0
def progerss_monitor(conn):
    global prog_mon
    prog_mon = 0
    while True:
        prog_mon_tmp = prog_mon
        time.sleep(1)
        if prog_mon == prog_mon_tmp:
            for i in range(65536-prog_mon):
                try:
                    conn.send(1)
                except BrokenPipeError:
                    pass
            break


is_recving = False
def scanner(udp_skt: socket.socket, addr: str, interval: float):
    global is_recving, prog_mon
    pbar = tqdm(iterable=range(65536), desc="Scaning progress",
                leave=False, unit="Port", unit_scale=False)
    
    if not is_recving:
        is_recving = True
        threading.Thread(target=recv_packets, args=(
            udp_skt, pbar), daemon=True).start()
        
    port_ranges = split_list(65536, mp.cpu_count() - 1)

    parent_conn, child_conn = mp.Pipe()

    threading.Thread(target=progerss_monitor, args=(
        child_conn,), daemon=True).start()

    for port_range in port_ranges:
        mp.Process(target=send_packet, args=(udp_skt, addr,
                   port_range, interval, child_conn), daemon=True).start()
        
    for p in pbar:
        parent_conn.recv()
        prog_mon += 1

    time.sleep(3)


def recv_packets(udp_skt, pbar):
    server_count = 0
    while True:
        try:
            infos, addr = parse_raw_pkt(udp_skt.recvfrom(1024))
            if not infos or not infos["motd"]:  # 过滤掉没有motd的和没有信息的
                continue

            server_count += 1

            values = [f"[Time   ] {getTime()}",
                      f"[Address] {infos['addr']}",
                      f"[MotdInf] {infos['motd']}",
                      f"[Version] {infos['version']}/{infos['version_id']}",
                      f"[GameInf] {infos['map']}/{infos['gamemode']}",
                      f"[Online ] {infos['online']}/{infos['max_player']}",
                      f"[Count  ] {server_count}",
                      ""]

            pbar.write("\n".join(values))
            scan_res.append(values)
        except socket.timeout:
            continue
        except ConnectionResetError:
            continue
        except OSError:
            if getattr(udp_skt, '_closed'):
                break
            traceback.print_exc()
            continue
        except:
            traceback.print_exc()
            continue


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("addr", help="the target server address")
    parser.add_argument("-i", "--interval", default=0.005, type=float,
                        help="send packet interval. recommand 0.01~0.0001")
    parser.add_argument("-p", "--port", default=random.randint(1024, 65535), type=int,
                        help="local port for send packet")

    args = parser.parse_args()

    addr = args.addr
    interval = args.interval
    local_port = args.port

    udp_skt = get_udp_socket(local_port)

    for addr in get_ip_list(addr):
        scanner(udp_skt, addr, interval)
