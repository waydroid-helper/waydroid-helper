import asyncio

from waydroid_helper.controller.core.control_msg import ControlMsg
from waydroid_helper.controller.core.event_bus import (Event, EventType,
                                                       EventBus)
from waydroid_helper.util.log import logger


class Server:
    def __init__(self, host: str = "0.0.0.0", port: int = 10721, event_bus: EventBus|None = None):
        self.host: str = host
        self.port: int = port
        self.message_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        if event_bus:
            self.event_bus = event_bus
        else:
            raise
        self.event_bus.subscribe(EventType.CONTROL_MSG, self.send_msg, subscriber=self)
        self.server: asyncio.Server | None = None
        self.writers: list[asyncio.StreamWriter] = []
        self.started_event = asyncio.Event()
        self.connected_event = asyncio.Event()
        self.disconnected_event = asyncio.Event()
        self.server_task: asyncio.Task[None] = asyncio.create_task(self.start_server())

        Server._initialized = True
        logger.info(f"Server singleton initialized on {host}:{port}")

    async def handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        if self.writers:
            writer.close()
            return
        self.writers.append(writer)
        outgoing = None
        incoming = None
        try:
            info = await asyncio.wait_for(reader.readexactly(64), 10)
            logger.info("Connected to %s", info.rstrip(b"\0").decode(errors="replace"))
            self.disconnected_event.clear()
            self.connected_event.set()
            # Even when the user is idle the peer can disappear (e.g. Android
            # stops). Watching its read side prevents stale taps being queued
            # and replayed on a later connection.
            outgoing = asyncio.create_task(self._write_messages(writer))
            incoming = asyncio.create_task(self._read_device_messages(reader))
            done, _ = await asyncio.wait((incoming, outgoing), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (ConnectionError, asyncio.IncompleteReadError, TimeoutError) as error:
            logger.info("Control socket closed: %s", error)
        finally:
            self.connected_event.clear()
            self.disconnected_event.set()
            tasks = [task for task in (incoming, outgoing) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            while not self.message_queue.empty():
                self.message_queue.get_nowait()
            writer.close()
            self.writers.remove(writer)

    async def _write_messages(self, writer):
        while (message := await self.message_queue.get()) is not None:
            writer.write(message)
            await writer.drain()

    async def _read_device_messages(self, reader):
        # This controller uses only host-to-device messages. Drain unsolicited
        # clipboard updates until EOF so the peer's write buffer cannot fill.
        while await reader.read(4096):
            pass

    async def start_server(self):
        try:
            self.server = await asyncio.start_server(self.handler, self.host, self.port)

            self.port = self.server.sockets[0].getsockname()[1]
            addrs = ", ".join(str(sock.getsockname()) for sock in self.server.sockets)
            logger.info(f"Serving on {addrs}")
            self.started_event.set()

            async with self.server:
                await self.server.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self.started_event.set() # Set event on failure to avoid deadlocks

    async def wait_started(self):
        await self.started_event.wait()

    async def close(self):
        await self.wait_started()
        if self.server:
            self.server.close()
            for writer in tuple(self.writers):
                self.message_queue.put_nowait(None)
                writer.close()
            await self.server.wait_closed()

        if not self.server_task.done():
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
        logger.info("Server closed.")

    def send(self, msg: bytes):
        """优化版本：直接使用 put_nowait，避免额外的函数调用开销"""
        try:
            self.message_queue.put_nowait(msg)
        except asyncio.QueueFull:
            # 如果队列满了，丢弃最旧的消息以避免阻塞
            try:
                self.message_queue.get_nowait()
                self.message_queue.put_nowait(msg)
            except asyncio.QueueEmpty:
                pass

    def send_msg(self, event: Event[ControlMsg]):
        """优化版本：减少日志调用和条件检查"""
        msg: ControlMsg = event.data
        # 只在需要时才调用 debug 日志（检查日志级别）
        if logger.isEnabledFor(10):  # DEBUG level = 10
            logger.debug("Send: %s", msg)

        if not self.connected_event.is_set():
            return

        # 优化后的 pack() 方法总是返回 bytes，无需检查 None
        packed_msg: bytes = msg.pack()
        self.send(packed_msg)
