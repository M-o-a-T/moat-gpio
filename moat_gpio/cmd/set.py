# -*- coding: utf-8 -*-

import trio

from trio_amqp import connect_amqp
from ..io_client import Output

import logging
logger = logging.getLogger(__name__)

async def run(config, port, value):
    amqp = dict(host='localhost', virtualhost='/moat')
    amqp.update(config.get('amqp',{}).get('server',{}))
    config = config['gpio']
    cfg = config.get('default',{})
    async with trio.open_nursery() as nursery:
        async with connect_amqp(**amqp) as amqp:
            cfg.update(config['out'].get('default',{}))
            try:
                cfg.update(config['out'][port])
            except KeyError:
                raise SyntaxError("Unknown port: %s" % (port,)) from None
            io = Output(**cfg)
            await io.run(amqp, value)
            logger.debug("Sent.")

