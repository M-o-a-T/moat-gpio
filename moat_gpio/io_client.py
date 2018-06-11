# INputs and outputs

import trio
import trio_gpio as gpio
import contextlib
from copy import deepcopy
from ._default import DEFAULT_QUEUE, DEFAULT_EXCHANGE, DEFAULT_ROUTE, DEFAULT_NAME
from json import loads as json_decode

class _io:
    def __init__(self, **cfg):
        self.chip = cfg['chip']
        self.pin = cfg['pin']
        D={'chip':self.chip, 'pin':self.pin, 'dir':self.dir}

        name = cfg.get('name', DEFAULT_NAME)
        self.name = name.format(**D)
        D['name']=self.name

        self.exch = cfg.get('exchange', DEFAULT_EXCHANGE).format(**D)
        self.exch_type = cfg.get('exchange_type', "topic")
        self.queue = cfg.get('queue', DEFAULT_QUEUE).format(**D)
        self.on_data = cfg.get('on', 'on')
        self.off_data = cfg.get('off', 'off')
        self.route = cfg.get('route', DEFAULT_ROUTE).format(**D)

        self.json_path = cfg.get('json', None)
        if isinstance(self.json_path,str) and self.json_path != '':
            self.json_path = self.json_path.split('.')

class Output(_io):
    """Represesent an Output pin: send a message to change the pin level."""
    dir='out'
    value=None

    def __init__(self, **cfg):
        super().__init__(**cfg)
        notify = cfg.get('notify','both')
        self.skip = set((0,1))
        if notify in ('both','up'):
            self.skip.remove(1)
        if notify in ('both','down'):
            self.skip.remove(0)

    async def run(self, amqp, value, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type)
            task_status.started()

            data = self.on_data if value else self.off_data
            data = data.format(dir='ack', chip=self.chip, pin=self.pin, name=self.name)
            data = data.encode("utf-8")

            await chan.basic_publish(data, exchange_name=self.exch, routing_key=self.route)


class Input(_io):
    """Represesent an Input pin: react whenever a specific AMQP message arrives."""
    dir='in'

    def __init__(self, **cfg):
        super().__init__(**cfg)
        self.on_data_reply = cfg.get('on', self.on_data)
        self.off_data_reply = cfg.get('off', self.off_data)

    async def run(self, amqp, chip, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type)
            if self.queue:
                res = await chan.queue_declare(queue_name=self.queue, durable=True, exclusive=True, auto_delete=False)
            else:
                res = await chan.queue_declare(queue_name=self.queue, durable=False, exclusive=True, auto_delete=True)
                self.queue = res.queue_name
            logger.debug("Bind %s %s %s", self.queue,self.exch,self.route)
            await chan.queue_bind(self.queue, self.exch, routing_key=self.route)

            pin = chip.line(self.pin)
            async with chan.new_consumer(self.queue) as listener:
                with pin.open(direction=gpio.DIRECTION_OUTPUT) as line:
                    task_status.started()

                    try:
                        async for body, envelope, properties in listener:
                            self.handle_msg(body, envelope, properties, line)
                    finally:
                        pin.value = 0

    async def handle_msg(self, body, envelope, properties, line):
        """Process one incoming message."""
        data = data.decode("utf-8")
        if self.json_path is not None:
            data = json_decode(data)
            for p in self.json_path:
                data = data[p]
        if data == self.on_data:
            print("on")
        elif data == self.off_data:
            print("off")
        else:
            logger.warn("%s: unknown data %s", self.exch,line.value)

