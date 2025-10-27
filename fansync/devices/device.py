# SPDX-License-Identifier: GPL-2.0-only
# Copyright 2025 Trevor Baker, all rights reserved.

from fansync import Fan, Light


class Device:
    """
    Not super happy w/ this arrangement. We'll see if it sticks.
    Basically this would be a friend class of Websocket? Need to get this
    working first and see how it feels to mess with it at the top layer
    """

    def __init__(self, display_name: str, device):
        self.display_name: str = display_name
        self.device: str = device

        self.lights: list[Light] = []
        self.fans: list[Fan] = []
