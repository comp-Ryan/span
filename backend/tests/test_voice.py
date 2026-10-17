import asyncio
from unittest.mock import AsyncMock

from owed.voice.live import Playback


def test_barge_in_cancels_audio_and_clears_queued_speech():
    async def check():
        ws = AsyncMock()
        playback = Playback(ws, 'stream-test')
        playback.current = asyncio.create_task(asyncio.sleep(30))
        await playback.queue.put('stale speech')
        await playback.interrupt()
        assert playback.current.cancelled()
        assert playback.queue.empty()
        ws.send_json.assert_awaited_once_with({'event': 'clear', 'streamSid': 'stream-test'})
    asyncio.run(check())
