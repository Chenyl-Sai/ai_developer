import queue, asyncio


class AsyncBatchQueue(asyncio.Queue):
    """支持批量操作的异步并发安全队列"""

    def __init__(self, maxsize=0):
        super().__init__(maxsize=maxsize)
        self._lock = asyncio.Lock()

    async def peek_all(self):
        """异步查看所有元素而不弹出"""
        async with self._lock:
            return list(self._queue)

    async def pop_all(self):
        """异步弹出所有元素并清空队列"""
        async with self._lock:
            items = list(self._queue)
            self._queue.clear()
            # 更新 unfinished_tasks
            self._unfinished_tasks -= len(items)
            return items

    async def pop_batch(self, max_items=None):
        """异步批量弹出指定数量的元素"""
        async with self._lock:
            items = []
            count = 0
            while self._queue and (max_items is None or count < max_items):
                item = self._queue.popleft()
                items.append(item)
                self._unfinished_tasks -= 1
                count += 1
            return items

    async def safe_put(self, item):
        """在持锁条件下安全放入元素"""
        async with self._lock:
            await super().put(item)

    async def safe_get(self):
        """在持锁条件下安全取出元素"""
        async with self._lock:
            item = await super().get()
            return item

    # 禁止直接调用 put
    async def put(self, item):
        raise RuntimeError("禁止直接调用 put，请使用 safe_put()")

class BatchQueue(queue.Queue):
    """支持批量操作的线程安全队列"""

    def peek_all(self):
        """查看所有元素而不弹出（线程安全）"""
        with self.mutex:
            return list(self.queue)

    def pop_all(self):
        """弹出所有元素并清空队列（线程安全）"""
        with self.mutex:
            items = list(self.queue)
            self.queue.clear()
            # 更新未完成任务计数
            self.unfinished_tasks -= len(items)
            return items

    def pop_batch(self, max_items=None):
        """批量弹出元素"""
        items = []
        count = 0

        while True:
            if max_items and count >= max_items:
                break
            try:
                with self.mutex:
                    if not self.queue:
                        break
                    item = self.queue.popleft()
                    items.append(item)
                    self.unfinished_tasks -= 1
                    count += 1
            except IndexError:
                break

        return items