# -*- coding: utf-8 -*-

from trio_amqp import connect_amqp

async def run(config):
    amqp = dict(host='localhost', virtualhost='/moat')
    amqp.update(config.get('amqp'.{}).get('server',{})
    async with connect_amqp(**amqp):
        
        
