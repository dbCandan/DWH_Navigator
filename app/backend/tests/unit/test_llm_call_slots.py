"""The process-wide chat slot limit (data-dictionary 003-llm-connection Requirement 17)."""

import asyncio
import threading

import pytest

from app.infrastructure.llm.call_slots import CallSlots

pytestmark = pytest.mark.unit


async def test_waiting_calls_get_slots_in_arrival_order() -> None:
    slots = CallSlots(1)
    await slots.acquire()
    order: list[int] = []

    async def waiter(number: int) -> None:
        await slots.acquire()
        order.append(number)
        slots.release()

    tasks = [asyncio.create_task(waiter(number)) for number in range(5)]
    await asyncio.sleep(0.01)
    assert order == []
    slots.release()
    await asyncio.gather(*tasks)
    assert order == [0, 1, 2, 3, 4]


async def test_a_cancelled_wait_leaves_the_queue_and_holds_nothing() -> None:
    slots = CallSlots(1)
    await slots.acquire()
    cancelled = asyncio.create_task(slots.acquire())
    second = asyncio.create_task(slots.acquire())
    await asyncio.sleep(0.01)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    slots.release()
    await asyncio.wait_for(second, 1)
    slots.release()
    # Both slots are free again: two acquisitions of a limit of one would block.
    await asyncio.wait_for(slots.acquire(), 1)


async def test_a_slot_granted_while_cancelling_is_passed_on() -> None:
    slots = CallSlots(1)
    await slots.acquire()
    racing = asyncio.create_task(slots.acquire())
    following = asyncio.create_task(slots.acquire())
    await asyncio.sleep(0.01)
    slots.release()  # grants ``racing`` on the next loop step ...
    racing.cancel()  # ... which is cancelled before it runs
    with pytest.raises(asyncio.CancelledError):
        await racing
    await asyncio.wait_for(following, 1)


async def test_the_limit_holds_across_event_loops_in_threads() -> None:
    slots = CallSlots(2)
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    async def use() -> None:
        await slots.acquire()
        try:
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.02)
            with lock:
                state["active"] -= 1
        finally:
            slots.release()

    def thread_main() -> None:
        async def many() -> None:
            await asyncio.gather(*(use() for _ in range(4)))

        asyncio.run(many())

    threads = [threading.Thread(target=thread_main) for _ in range(3)]
    for thread in threads:
        thread.start()
    await asyncio.gather(*(use() for _ in range(4)))
    for thread in threads:
        thread.join(5)
    assert state["peak"] == 2


def test_the_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        CallSlots(0)
