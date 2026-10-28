"""Errors exposed by the 352 X83 integration."""


class Air352Error(Exception):
    """Base integration error."""


class AuthenticationError(Air352Error):
    """The persisted old-352 session is no longer accepted."""


class CannotConnectError(Air352Error):
    """The verified cloud connection could not be established."""


class ProtocolError(Air352Error):
    """A frame or response violated the audited protocol boundary."""


class ControlStateNotConfirmedError(Air352Error):
    """No matching device frame confirmed a requested control state."""


class PowerStateNotConfirmedError(ControlStateNotConfirmedError):
    """No matching device frame confirmed the requested power state."""
