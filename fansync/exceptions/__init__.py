# SPDX-License-Identifier: GPL-2.0-only
# Copyright 2025 Trevor Baker, all rights reserved.



class AuthFailed (BaseException):
    pass


class WebsocketAuthException(Exception):
    pass

class WebsocketAlreadyConnectedException(Exception):
    pass


class TimedOutException(Exception):
    pass
