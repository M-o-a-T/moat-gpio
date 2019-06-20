# -*- coding: utf-8 -*-

import math
import anyio

from asyncamqp import connect_amqp
from ..io import Chips,Input,Output,Pulse

import logging
logger = logging.getLogger(__name__)

async def run(config):
    amqp = dict(host='localhost', virtualhost='/moat')
    amqp.update(config.get('amqp',{}).get('server',{}))
    config = config['gpio']
    D = config.get('default',{})
    async with anyio.create_task_group() as tg:
        with Chips() as chips:
            async with connect_amqp(**amqp) as amqp:
                for ios,cls in (('in',Input),('out',Output),('pulse',Pulse)):
                    ios = config.get(ios, {})
                    DD = D.copy()
                    DD.update(ios.pop('default',{}))
                    for key,io in ios.items():
                        cfg = DD.copy()
                        if cls.has_default:
                            d = io.get('default',{})
                            cfg.update(d)
                            io['default'] = cfg
                            cfg = io
                        else:
                            cfg.update(io)
                        io = cls(key, **cfg)
                        started = anyio.create_event()
                        await tg.spawn(io.run, amqp, chips, tg, started)
                        await started.wait()
                logger.info("Running.")
                await anyio.sleep(math.inf)

