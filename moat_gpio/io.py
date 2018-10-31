# INputs and outputs

import trio
import trio_gpio as gpio
import contextlib
from copy import deepcopy
from ._default import DEFAULT_QUEUE, DEFAULT_EXCHANGE, DEFAULT_ROUTE, DEFAULT_NAME
from json import loads as json_decode

import logging
logger = logging.getLogger(__name__)

FLAGS = {'high':0, 'low':gpio.REQUEST_FLAG_ACTIVE_LOW}
BIAS = {'none':0, 'high':gpio.REQUEST_FLAG_OPEN_DRAIN, 'low':gpio.REQUEST_FLAG_OPEN_SOURCE}

class _io:
    has_default = False
    is_sub = False

    def __init__(self, key, **cfg):
        self.chip = cfg['chip']
        self.pin = cfg['pin']
        D={'chip':self.chip, 'pin':self.pin, 'dir':self.dir, 'key':key}

        name = cfg.get('name', DEFAULT_NAME)
        self.name = name.format(**D)
        D['name']=self.name

        if self.is_sub:
            self.data = cfg.get('data', key)
        else:
            self.exch = cfg.get('exchange', DEFAULT_EXCHANGE).format(**D)
            self.exch_type = cfg.get('exchange_type', "topic")
            self.queue = cfg.get('queue', DEFAULT_QUEUE).format(**D)

            self.on_data = cfg.get('on', 'on')
            self.off_data = cfg.get('off', 'off')
            self.route = cfg.get('route', DEFAULT_ROUTE).format(**D)

            self.json_path = cfg.get('json', None)
            if isinstance(self.json_path,str) and self.json_path != '':
                def elem(k):
                    try:
                        return int(k)
                    except ValueError:
                        return k
                self.json_path = [ elem(k) for k in self.json_path.split('.') ]

class Input(_io):
    """Represesent an Input pin: send a message whenever a pin level changes."""
    dir='in'
    value=None

    def __init__(self, key, **cfg):
        super().__init__(key, **cfg)
        notify = cfg.get('notify','both')
        self.debounce = float(cfg.get('debounce',0.2))
        self.skip = set((0,1))
        self.flags = FLAGS[cfg.get('active','high')]
        if notify in ('both','up'):
            self.skip.remove(1)
        if notify in ('both','down'):
            self.skip.remove(0)

    async def debouncer(self, chan, q, task_status=trio.TASK_STATUS_IGNORED):
        task_status.started()
        while True:
            e = await q.get()
            logger.debug("new %s %s", self.name,e1)
            val = not self.value
            # something happens. Send an event immediately,
            # no matter the event's value.
            await self.handle_event(val, chan)

            while True:
                with trio.move_on_after(self.debounce) as skip:
                    e = await q.get()
                if skip.cancelled_caught:
                    break

            logger.debug("done %s %s", self.name,e)
            # If the signal was shorter than debounce, reset.
            if e.value != val:
                await self.handle_event(e.value, chan)

    async def run(self, amqp, chips, nursery, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        chip = chips.add(self.chip)
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type, durable=True)
            pin = chip.line(self.pin)
            with chip.line(self.pin).monitor(gpio.REQUEST_EVENT_BOTH_EDGES, flags=self.flags) as pin:
                q = trio.Queue(0)
                await nursery.start(self.debouncer, chan, q)
                task_status.started()

                logger.debug("Mon started %s %s %d", self.name, self.chip,self.pin)
                async for evt in pin:
                    logger.debug("see %s %s", self.name,evt)
                    await q.put(evt)

    async def handle_event(self, val, chan):
        """Process a single event."""
        self.value = val
        if val in self.skip:
            logger.debug("Skip %s %s",self.name,val)
            return
        logger.debug("Send %s %s",self.name,val)
        data = self.on_data if val else self.off_data
        data = data.format(dir='in', chip=self.chip, pin=self.pin, name=self.name)
        data = data.encode("utf-8")

        logger.debug("Pub %s to %s %s",repr(data), self.exch, self.route)
        await chan.basic_publish(payload=data, exchange_name=self.exch, routing_key=self.route)

class Output(_io):
    """Represesent an Output pin: change a pin whenever a specific AMQP message arrives."""
    dir='out'

    def __init__(self, key, **cfg):
        super().__init__(key, **cfg)
        self.on_data_reply = cfg.get('on', self.on_data)
        self.off_data_reply = cfg.get('off', self.off_data)
        self.exch_reply = cfg.get('reply_exch', "")

        D={'chip':self.chip, 'pin':self.pin, 'dir':self.dir, 'key':key, 'name':self.name}
        self.state_exch = cfg.get('state_exchange', self.exch).format(**D)
        self.state_exch_type = cfg.get('state_exchange_type', self.exch_type)
        self.state_route = cfg.get('state_route', '').format(**D)
        self.flags = FLAGS[cfg.get('active','high')]
        self.flags |= BIAS[cfg.get('bias','none')]

    async def run(self, amqp, chips, nursery, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        chip = chips.add(self.chip)
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type, durable=True)
            if self.state_exch:
                await chan.exchange_declare(self.state_exch, self.state_exch_type, durable=True)
            res = await chan.queue_declare(queue_name=self.queue, durable=False, exclusive=True, auto_delete=True)
            self.queue = res['queue']
            logger.debug("Bind %s %s %s", self.queue,self.exch,self.route)
            await chan.queue_bind(self.queue, self.exch, routing_key=self.route)

            pin = chip.line(self.pin)
            async with chan.new_consumer(self.queue) as listener:
                with pin.open(direction=gpio.DIRECTION_OUTPUT, flags=self.flags) as line:
                    line.value = 0
                    task_status.started()

                    try:
                        async for body, envelope, properties in listener:
                            await self.handle_msg(chan, body, envelope, properties, line)
                    finally:
                        line.value = 0

    async def handle_msg(self, chan, body, envelope, properties, line):
        """Process one incoming message."""
        logger.debug("output %s: %s with json %s",self.name, body, self.json_path)
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
        data = self.on_data_reply if value else self.off_data_reply
        data = data.format(dir='ack', chip=self.chip, pin=self.pin, name=self.name)
        data = data.encode("utf-8")

        if properties.reply_to:
            await chan.basic_publish(
                payload=data,
                exchange_name=self.exchange_reply,
                routing_key=properties.reply_to,
                properties={
                    'correlation_id': properties.correlation_id,
                },
            )

        await chan.basic_client_ack(delivery_tag=envelope.delivery_tag)

        if self.state_route:
            await chan.basic_publish(
                payload=data,
                exchange_name=self.state_exch,
                routing_key=self.state_route,
            )

class Pulse:
    """Represent a number of Output pins: message X pulses the pin named X.
    Only one output pin is active at any time."""
    has_default = True

    def __init__(self, key, **cfg):
        self.outputs = {}
        d = cfg.pop('default')

        D = {'key':key}
        name = d.get('key', DEFAULT_NAME)
        self.name = name.format(**D)
        D['group']=self.name

        self.exch = d.get('exchange', DEFAULT_EXCHANGE).format(**D)
        self.exch_type = d.get('exchange_type', "topic")
        self.queue = d.get('queue', DEFAULT_QUEUE).format(**D)
        self.route = d.get('route', DEFAULT_ROUTE).format(**D)
        self.state_exch = d.get('state_exchange', self.exch).format(**D)
        self.state_exch_type = d.get('state_exchange_type', self.exch_type)
        self.state_route = d.get('state_route', '').format(**D)
        self.exch_reply = d.get('reply_exch', "")

        self.json_path = d.get('json', None)
        if isinstance(self.json_path,str) and self.json_path != '':
            def elem(k):
                try:
                    return int(k)
                except ValueError:
                    return k
            self.json_path = [ elem(k) for k in self.json_path.split('.') ]

        for k,v in cfg.items():
            cfg = d.copy()
            cfg.update(v)
            self.outputs[k] = SubOutput(k, **cfg)

    async def run(self, amqp, chips, nursery, task_status=trio.TASK_STATUS_IGNORED):
        queues = {}
        for k,v in self.outputs.items():
            q,r = (trio.Queue(0), trio.Queue(0))
            queues[k] = v
            await nursery.start(v.run_sub, chips, q,r)
        
        async with amqp.new_channel() as chan:
            await chan.exchange_declare(self.exch, self.exch_type, durable=True)
            if self.state_exch:
                await chan.exchange_declare(self.state_exch, self.state_exch_type, durable=True)
            res = await chan.queue_declare(queue_name=self.queue, durable=False, exclusive=True, auto_delete=True)
            self.queue = res['queue']
            logger.debug("Bind %s %s %s", self.queue,self.exch,self.route)
            await chan.queue_bind(self.queue, self.exch, routing_key=self.route)

            async with chan.new_consumer(self.queue) as listener:
                task_status.started()
                async for body, envelope, properties in listener:
                    await self.handle_msg(chan, queues, body, envelope, properties)

    async def handle_msg(self, chan, queues, body, envelope, properties):
        """Process one incoming message."""
        data = body.decode("utf-8")
        if self.json_path is not None:
            data = json_decode(data)
            for p in self.json_path:
                data = data[p]
        try:
            output = queues[data]
        except KeyError:
            logger.warn("%s: unknown data %s", self.exch, repr(data))
            await chan.basic_client_nack(delivery_tag=envelope.delivery_tag)
            return
        logger.debug("pulse %s",output.name)
        await output.queue.put(None)
        await output.reply_queue.get()
        logger.debug("pulse %s done",output.name)

        # reply?
        data = output.data_reply
        data = data.format(dir='ack', chip=output.chip, pin=output.pin, name=output.name, group=self.name)
        data = data.encode("utf-8")

        if properties.reply_to:
            await chan.basic_publish(
                payload=data,
                exchange_name=self.exchange_reply,
                routing_key=properties.reply_to,
                properties={
                    'correlation_id': properties.correlation_id,
                },
            )

        await chan.basic_client_ack(delivery_tag=envelope.delivery_tag)

        if self.state_route:
            await chan.basic_publish(
                payload=data,
                exchange_name=self.state_exch,
                routing_key=self.state_route,
            )

class SubOutput(_io):
    dir='out'
    is_sub = True

    def __init__(self, key, **cfg):
        super().__init__(key, **cfg)

        self.data_reply = cfg.get('reply', self.data)
        self.on_time = cfg.get('on_time', 1)
        self.off_time = cfg.get('off_time', 1)
        self.flags = FLAGS[cfg.get('active','high')]
        self.flags |= BIAS[cfg.get('bias','none')]

    async def run_sub(self, chips, queue, reply_queue, task_status=trio.TASK_STATUS_IGNORED):
        """Task handler for processing this output."""
        self.queue = queue
        self.reply_queue = reply_queue

        chip = chips.add(self.chip)
        pin = chip.line(self.pin)
        with pin.open(direction=gpio.DIRECTION_OUTPUT, flags=self.flags) as line:
            task_status.started()
            async for m in queue:
                line.value = 1
                try:
                    await trio.sleep(self.on_time)
                finally:
                    line.value = 0
                await trio.sleep(self.off_time)
                await reply_queue.put(None)


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
