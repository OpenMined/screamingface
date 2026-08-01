"""Benchmark assets baked into the Runner image.

The control plane imports only static manifest assets. Preparation runs at image build, while
aggregation is invoked through a declared ``[commands]`` route; neither side hand-wires runtime
handlers into a ``Url4Node``.
"""
