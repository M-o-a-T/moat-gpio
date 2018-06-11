# INputs and outputs

import trio
import trio_gpio as gpio
import contextlib
from copy import deepcopy
from ._default import DEFAULT_QUEUE, DEFAULT_EXCHANGE, DEFAULT_ROUTE, DEFAULT_NAME
from json import loads as json_decode

import logging
logger = logging.getLogger(__name__)

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
            with chip.line(self.pin).monitor(gpio.REQUEST_EVENT_BOTH_EDGES) as pin:
                task_status.started()

                logger.debug("Mon started %s %d", self.chip,self.pin)
                async for evt in pin:
                    logger.debug("Mon Evt %s %d =%s", self.chip,self.pin, evt)
                    await self.handle_event(evt, chan)

    async def handle_event(self, e, chan):
        """Process a single event."""
        self.value = e.value
        if e.value in self.skip:
            return
        data = self.on_data if e.value else self.off_data
        data = data.format(dir='in', chip=self.chip, pin=self.pin, name=self.name)
        data = data.encode("utf-8")

        logger.debug("Pub %s to %s %s",repr(data), self.exch, self.route)
        await chan.basic_publish(payload=data, exchange_name=self.exch, routing_key=self.route)


class Output(_io):
    """Represesent an Output pin: change a pin whenever a specific AMQP message arrives."""
    dir='out'

    def __init__(self, **cfg):
        super().__init__(**cfg)
        self.on_data_reply = cfg.get('on', self.on_data)
        self.off_data_reply = cfg.get('off', self.off_data)
        self.exch_reply = cfg.get('exch_reply', "")

    async def run(self, amqp, chip, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type)
            res = await chan.queue_declare(queue_name=self.queue, durable=False, exclusive=True, auto_delete=True)
            self.queue = res['queue']
            logger.debug("Bind %s %s %s", self.queue,self.exch,self.route)
            await chan.queue_bind(self.queue, self.exch, routing_key=self.route)

            pin = chip.line(self.pin)
            async with chan.new_consumer(self.queue) as listener:
                with pin.open(direction=gpio.DIRECTION_OUTPUT) as line:
                    task_status.started()

                    try:
                        async for body, envelope, properties in listener:
                            await self.handle_msg(chan, body, envelope, properties, line)
                    finally:
                        line.value = 0

    async def handle_msg(self, chan, body, envelope, properties, line):
        """Process one incoming message."""
        data = body.decode("utf-8")
        if self.json_path is not None:
            data = json_decode(data)
            for p in self.json_path:
                data = data[p]
        if data == self.on_data:
            line.value = value = 1
        elif data == self.off_data:
            line.value = value = 0
        else:
            logger.warn("%s: unknown data %s", self.exch,line.value)
            await chan.basic_client_nack(delivery_tag=envelope.delivery_tag)
            return
        logger.debug("set %s to %s",self.name, value)

        # reply?
        if properties.reply_to:
            data = self.on_data_reply if value else self.off_data_reply
            data = data.format(dir='ack', chip=self.chip, pin=self.pin, name=self.name)
            data = data.encode("utf-8")

            await self.chan.basic_publish(
                payload=data,
                exchange_name=self.exchange_reply,
                routing_key=properties.reply_to,
                properties={
                    'correlation_id': properties.correlation_id,
                },
            )

        await chan.basic_client_ack(delivery_tag=envelope.delivery_tag)


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
