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
        self.exch_type = cfg.get('exchange_type', "topic").format(**D)
        self.queue = cfg.get('queue', DEFAULT_QUEUE).format(**D)
        self.on_data = cfg.get('on', 'on')
        self.off_data = cfg.get('off', 'off')
        self.route = cfg.get('route', DEFAULT_ROUTE).format(**D)

        self.json_path = cfg.get('json', None)
        if isinstance(self.json_path,str) and self.json_path != '':
            self.json_path = self.json_path.split('.')

class Input(_io):
    """Represesent an Input pin: send a message whenever a pin level changes."""
    dir='in'
    value=None

    def __init__(self, **cfg):
        super().__init__(**cfg)
        notify = cfg.get('notify','both')
        self.skip = set((0,1))
        if notify in ('both','up'):
            self.skip.remove(1)
        if notify in ('both','down'):
            self.skip.remove(0)

    async def run(self, amqp, chip, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type)
            pin = chip.line(self.pin)
            with pin.monitor(gpio.REQUEST_EVENT_BOTH_EDGES):
                task_status.started()

                async for evt in pin:
                    await self.handle_event(e, chan)

    async def handle_event(self, e):
        """Process a single event."""
        self.value = e.value
        if e.value in self.skip:
            return
        data = self.on_data if e.value else self.off_data
        data = data.format(dir='in', chip=self.chip, pin=self.pin, name=self.name)
        data = data.encode("utf-8")

        await chan.basic_publish(data, exchange_name=self.exch, routing_key=self.route)


class Output(_io):
    dir='out'
    """Represesent an Output pin: change a pin whenever a specific AMQP message arrives."""
    async def run(self, amqp, chip, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type)
            await chan.queue_declare(queue_name=self.queue)
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
            line.value = 1
        elif data == self.off_data:
            line.value = 0
        else:
            logger.warn("%s: unknown data %s", self.exch,line.value)

        await chan.basic_publish(data)


class Chips(contextlib.ExitStack):
    """This context manager caches opened chips:
       if you have more than one pins on a chip, the chip is only opened once.
       """
    def __enter__(self):
        self.chips = {}
        return super().__enter__()
    
    def __exit__(self, *tb):
        self.chips = {}
        super().__exit__(*tb)

    def add(self, chip):
        try:
            return self.chips[chip]
        except KeyError:
            if isinstance(chip,str):
                c = gpio.Chip(label=chip)
            else:
                c = gpio.Chip(num=chip)
            c = self.enter_context(c)
            return c

#    def io_generate(self, cfg):
#        """This iterator generates a list of I/O objects for you to run."""
#        setup = {'bus':{'queue':DEFAULT_QUEUE, 'exchange':DEFAULT_EXCHANGE, 'on':'on', 'off':'off', 'route':DEFAULT_ROUTE}}
#        setup.update(cfg.get('bus',{}))
#        c1 = cfg.get('input',{})
#        s1 = deepcopy(setup)
#        s1['bus'].update(c1.get('bus',{}))
#        for c in c1.get('lines',()):
#            s2 = deepcopy(s1)
#            s2.update(c)
#            yield Input(s2)
#
#        c1 = cfg.get('output',{})
#        s1 = deepcopy(setup)
#        s1['bus'].update(c1.get('bus',{}))
#        for c in c1.get('lines',()):
#            s2 = deepcopy(s1)
#            s2.update(c)
#            yield Output(c2)
#
#    async def run(self, cfg, task_status=TASK_STATUS_IGNORED):
#        with self as c:
#            async with trio.open_nursery as n:
#                for pin in self.io_generate(cfg):
#                    n.start_soon(pin.run)
#
#
