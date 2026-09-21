"""
Custom Gateway Provider Plugin Example for Omnididact.
Demonstrates how to add an enterprise / private LLM gateway via plugins.
"""
from typing import Callable

def register(register_func: Callable):
    from plugins.custom_gateway_example.provider import CustomGatewayProvider
    register_func("custom_gateway", CustomGatewayProvider)
