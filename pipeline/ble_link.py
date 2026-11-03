"""Bluetooth hop for Pipeline A (CPAP device -> phone), built with Bumble.

Done by Bumble: connecting, pairing and keeping the bond (pairing keys),
encrypting a reconnection with the saved keys, sending the rows as BLE
notifications, and disconnecting.
Decided by our code: whether the link is up in a given minute (Bumble cannot
simulate link loss), and unpair(), which deletes the keys to model a broken bond.
"""
import asyncio
import json

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

LOOP = asyncio.new_event_loop()   # one event loop shared by every link


class BleLink:
    """One CPAP device and its paired phone."""

    def __init__(self, n):
        LOOP.run_until_complete(self._setup(n))

    async def _setup(self, n):
        link = LocalLink()
        a_cpap, a_phone = f"F0:00:00:00:00:{n:02X}", f"F1:00:00:00:00:{n:02X}"
        c_cpap = Controller(f"cpap{n}", link=link, public_address=a_cpap)
        c_phone = Controller(f"phone{n}", link=link, public_address=a_phone)
        self.cpap = Device(address=Address(a_cpap), host=Host(c_cpap, AsyncPipeSink(c_cpap)))
        self.phone = Device(address=Address(a_phone), host=Host(c_phone, AsyncPipeSink(c_phone)))
        self.cpap.keystore, self.phone.keystore = MemoryKeyStore(), MemoryKeyStore()

        self.payload = b""
        self.data = Characteristic(DATA_UUID, Characteristic.Properties.NOTIFY,
                                   Characteristic.READABLE, b"")
        control = Characteristic(CONTROL_UUID, Characteristic.Properties.WRITE,
                                 Characteristic.WRITEABLE, CharacteristicValue(write=self._on_control))
        self.cpap.add_service(Service(SERVICE_UUID, [control, self.data]))
        await self.cpap.power_on()
        await self.phone.power_on()

    def _on_control(self, connection, value):
        if value == b"SYNC":
            LOOP.create_task(self._send_all(connection))

    async def _send_all(self, connection):
        for i in range(0, len(self.payload), CHUNK):
            await self.cpap.notify_subscriber(connection, self.data, self.payload[i:i + CHUNK])
        await self.cpap.notify_subscriber(connection, self.data, b"END")

    # ---- used by pipeline_a.py ----
    def pair(self):
        """Pairs the phone with the CPAP device (first setup, or a manual re-pair)."""
        return self.transfer([], pair=True)

    def is_bonded(self):
        return bool(LOOP.run_until_complete(self.phone.keystore.get_all()))

    def unpair(self):
        """Deletes the pairing keys on both sides: the bond is broken."""
        LOOP.run_until_complete(self.phone.keystore.delete_all())
        LOOP.run_until_complete(self.cpap.keystore.delete_all())

    def transfer(self, rows, pair=False):
        """Sends rows from the CPAP device to the phone over BLE. Returns what the phone received."""
        return LOOP.run_until_complete(self._transfer(rows, pair))

    # ---- one BLE session ----
    async def _transfer(self, rows, pair):
        self.payload = json.dumps(rows).encode()
        await self.cpap.start_advertising(advertising_interval_min=1.0)
        conn = await asyncio.wait_for(self.phone.connect(self.cpap.random_address), 5)
        try:
            if pair:
                await conn.pair()
                await self._remember(self.phone, self.cpap.random_address)
                await self._remember(self.cpap, self.phone.random_address)
            else:
                await conn.encrypt()   # uses the saved keys; fails if the bond is gone
            peer = Peer(conn)
            await peer.request_mtu(247)
            await peer.discover_services([SERVICE_UUID])
            await peer.discover_characteristics([], peer.get_services_by_uuid(SERVICE_UUID)[0])
            data_c = peer.get_characteristics_by_uuid(DATA_UUID)[0]
            ctrl_c = peer.get_characteristics_by_uuid(CONTROL_UUID)[0]

            chunks, done = [], LOOP.create_future()

            def on_chunk(value):
                if value == b"END":
                    if not done.done():
                        done.set_result(True)
                else:
                    chunks.append(bytes(value))

            await peer.subscribe(data_c, on_chunk)
            await peer.write_value(ctrl_c, b"SYNC", with_response=True)
            await asyncio.wait_for(done, 10)
            return json.loads(b"".join(chunks).decode())
        finally:
            await conn.disconnect()
            await self.cpap.stop_advertising()

    @staticmethod
    async def _remember(device, peer_address):
        """Saves the bond under the address the peer reconnects from."""
        for _name, keys in await device.keystore.get_all():
            await device.keystore.update(str(peer_address), keys)