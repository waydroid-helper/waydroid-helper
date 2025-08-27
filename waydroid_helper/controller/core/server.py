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
        self.server_task: asyncio.Task[None] = asyncio.create_task(self.start_server())

        Server._initialized = True
        logger.info(f"Server singleton initialized on {host}:{port}")

    async def handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info("peername")
        logger.info(f"Connected to {addr!r}")
        info = await reader.read(64)
        logger.info(f"Connected to {info.decode()}")
        self.writers.append(writer)

        try:
            while True:
                message = await self.message_queue.get()
                if not message:
                    break
                writer.write(message)
        finally:
            logger.info(f"Closing the connection to {addr!r}")
            self.writers.remove(writer)
            writer.close()
            await writer.wait_closed()

    async def start_server(self):
        try:
            self.server = await asyncio.start_server(self.handler, self.host, self.port)

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

    def close(self):
        if self.server:
            asyncio.create_task(self._close())

    async def _close(self):
        if not self.server:
            return

        self.server.close()
        await self.server.wait_closed()

        # Wake up handlers to exit
        await self.message_queue.put(None)

        # Close all client connections
        for writer in self.writers:
            if not writer.is_closing():
                writer.close()
                await writer.wait_closed()

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

        # 优化后的 pack() 方法总是返回 bytes，无需检查 None
        packed_msg: bytes = msg.pack()
        self.send(packed_msg)
