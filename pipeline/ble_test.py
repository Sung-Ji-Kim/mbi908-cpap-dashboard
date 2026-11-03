import asyncio

from bumble.controller import Controller
from bumble.device import Device, Peer
from bumble.gatt import Characteristic, CharacteristicValue, Service
from bumble.hci import Address
from bumble.host import Host
from bumble.keys import MemoryKeyStore
from bumble.link import LocalLink
from bumble.transport.common import AsyncPipeSink

SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
CONTROL_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   # phone writes b"SYNC"
DATA_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"      # CPAP sends data chunks
CHUNK = 240


async def main():
    loop = asyncio.get_running_loop()

    # 1. Two virtual devices on one virtual radio link
    link = LocalLink()
    c_cpap = Controller("cpap", link=link, public_address="F0:F0:F0:F0:F0:F0")
    c_phone = Controller("phone", link=link, public_address="F1:F1:F1:F1:F1:F1")
    cpap = Device(address=Address("F0:F0:F0:F0:F0:F0"), host=Host(c_cpap, AsyncPipeSink(c_cpap)))
    phone = Device(address=Address("F1:F1:F1:F1:F1:F1"), host=Host(c_phone, AsyncPipeSink(c_phone)))
    cpap.keystore, phone.keystore = MemoryKeyStore(), MemoryKeyStore()

    # 2. The CPAP device offers a GATT service with two characteristics
    payload = ("x" * 1000).encode()          # stands in for one night of minute rows
    data = Characteristic(DATA_UUID, Characteristic.Properties.NOTIFY, Characteristic.READABLE, b"")

    async def send_all(connection):
        for i in range(0, len(payload), CHUNK):
            await cpap.notify_subscriber(connection, data, payload[i:i + CHUNK])
        await cpap.notify_subscriber(connection, data, b"END")

    def on_control(connection, value):
        if value == b"SYNC":
            loop.create_task(send_all(connection))

    control = Characteristic(CONTROL_UUID, Characteristic.Properties.WRITE,
                             Characteristic.WRITEABLE, CharacteristicValue(write=on_control))
    cpap.add_service(Service(SERVICE_UUID, [control, data]))
    await cpap.power_on()
    await phone.power_on()
    print("1. devices on")

    # 3. The phone connects and pairs
    await cpap.start_advertising(advertising_interval_min=1.0)
    conn = await asyncio.wait_for(phone.connect(cpap.random_address), 5)
    print("2. connected")
    await asyncio.wait_for(conn.pair(), 10)
    print("3. paired, keys saved:", [name for name, _ in await phone.keystore.get_all()])

    # 4. The phone asks for the data and collects the chunks
    peer = Peer(conn)
    await peer.request_mtu(247)
    await peer.discover_services([SERVICE_UUID])
    await peer.discover_characteristics([], peer.get_services_by_uuid(SERVICE_UUID)[0])
    data_c = peer.get_characteristics_by_uuid(DATA_UUID)[0]
    ctrl_c = peer.get_characteristics_by_uuid(CONTROL_UUID)[0]

    chunks, done = [], loop.create_future()

    def on_chunk(value):
        if value == b"END":
            done.set_result(True)
        else:
            chunks.append(bytes(value))

    await peer.subscribe(data_c, on_chunk)
    await peer.write_value(ctrl_c, b"SYNC", with_response=True)
    await asyncio.wait_for(done, 10)
    received = sum(len(c) for c in chunks)
    print(f"4. phone received {received} bytes in {len(chunks)} chunks")

    # 5. Disconnect
    await conn.disconnect()
    print("5. disconnected")
    print("OK" if received == len(payload) else "CHECK")


asyncio.run(main())