# -*- coding: utf-8 -*-

import math
import trio

from trio_amqp import connect_amqp
from ..io import Chips,Input,Output,Pulse

import logging
logger = logging.getLogger(__name__)

async def run(config):
    amqp = dict(host='localhost', virtualhost='/moat')
    amqp.update(config.get('amqp',{}).get('server',{}))
    config = config['gpio']
    D = config.get('default',{})
    async with trio.open_nursery() as nursery:
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
                        await nursery.start(io.run, amqp, chips, nursery)
                logger.info("Running.")
                await trio.sleep(math.inf)

