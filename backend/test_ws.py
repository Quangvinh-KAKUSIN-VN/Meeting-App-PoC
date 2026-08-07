import asyncio, websockets, numpy as np

async def main():
    url = "ws://127.0.0.1:8765/ws/audio/ja?source=system"
    async with websockets.connect(url) as ws:
        print("✅ Kết nối OK")
        silence = (np.zeros(16000, dtype=np.int16)).tobytes()
        for _ in range(5):
            await ws.send(silence)
            await asyncio.sleep(0.1)
        print("✅ Gửi audio OK — backend hoàn toàn bình thường")

asyncio.run(main())