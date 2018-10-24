"""This module implements the AppFutures.

We have two basic types of futures:
    1. DataFutures which represent data objects
    2. AppFutures which represent the futures on App/Leaf tasks.

"""

from concurrent.futures import Future
import logging
import threading

from parsl.app.errors import RemoteException

logger = logging.getLogger(__name__)

# Possible future states (for internal use by the futures package).
PENDING = 'PENDING'
RUNNING = 'RUNNING'
# The future was cancelled by the user...
CANCELLED = 'CANCELLED'
# ...and _Waiter.add_cancelled() was called by a worker.
CANCELLED_AND_NOTIFIED = 'CANCELLED_AND_NOTIFIED'
FINISHED = 'FINISHED'

_STATE_TO_DESCRIPTION_MAP = {
    PENDING: "pending",
    RUNNING: "running",
    CANCELLED: "cancelled",
    CANCELLED_AND_NOTIFIED: "cancelled",
    FINISHED: "finished"
}


class AppFuture(Future):
    """An AppFuture wraps a sequence of Futures which may fail and be retried.

    TODO: what causes the retries? something in the DFK, not inside here, I guess?

    An AppFuture starts with no parent future. A sequence of parent futures may
    be assigned by code outside of this class, by passing that new parent future
    into "update_future".

    TODO: is it an error to update the parent future when we already have a result?
    It should be, and this class should catch it - in a thread-safe manner.

    The AppFuture will set its result to the result of the parent future, if that
    parent future completes without an exception. This result setting (should/will/TODO)
    cause .result(), .exception() and done callbacks to fire as expected when a
    Future has a result set.

    The AppFuture will not set its result to the result of the parent future, if
    that parent future completes with an exception, and if that parent future
    has retries left. In that case, no result(), exception() or done callbacks (should/will/TODO)
    report a result.

    The AppFuture will set its result to the result of the parent future, if that
    parent future completes with an exception and if that parent future has no
    retries left, or if it has no retry field. .result(), .exception() and done callbacks
    will/should/TODO give a result as expected when a Future has a result set

    The parent future may return a RemoteException as a result (rather than raising it
    as an exception) and AppFuture will treat this an an exception for the above
    retry and result handling behaviour.

    """

    def __init__(self, parent, tid=None, stdout=None, stderr=None):
        """Initialize the AppFuture.

        Args:
             - parent (Future) : The parent future if one exists
               A default value of None should be passed in if app is not launched

        KWargs:
             - tid (Int) : Task id should be any unique identifier. Now Int.
             - stdout (str) : Stdout file of the app.
                   Default: None
             - stderr (str) : Stderr file of the app.
                   Default: None
        """
        logger.debug("BENC: creating AppFuture")
        self._tid = tid
        super().__init__()
        self.prev_parent = None
        self.parent = None
        self._update_lock = threading.Lock()
        self._parent_update_event = threading.Event()
        self._outputs = []
        self._stdout = stdout
        self._stderr = stderr

        if parent is not None:
            self.update_parent(parent)

    def parent_callback(self, executor_fu):
        """Callback from a parent future to update the AppFuture.

        Used internally by AppFuture, and should not be called by code using AppFuture.

        Args:
            - executor_fu (Future): Future returned by the executor along with callback.
              This may not be the current parent future, as the parent future may have 
              already been updated to point to a retrying execution, and in that case,
              this is logged.

              In the case that a new parent has been attached, we must immediately discard
              this result no matter what it contains (although it might be interesting
              to log if it was successful...)

        Returns:
            - None

        Updates the super() with the result() or exception()
        """
        # print("[RETRY:TODO] parent_Callback for {0}".format(executor_fu))
        logger.debug("AppFuture parent_callback firing for AppFuture self={}".format(self))
        with self._update_lock:

            if not executor_fu.done():
                logger.error("BENC: callback future was not done, despite being passed to done callback")
                raise ValueError("done callback called, despite future not reporting itself as done")

            if executor_fu != self.parent:
                logger.debug("parent_callback fired with parameter future that is not the current parent future: current parent future is {}, callback parameter future is {} - checking that we got an exception not a result".format(self.parent, executor_fu))

                if executor_fu.exception() is None and not isinstance(executor_fu.result(), RemoteException):
                    # ... then we completed with a value, not an exception or wrapped exception,
                    # but we've got an updated executor future.
                    # This is bad - for example, we've started a retry even though we have a result

                    logger.error("BENC: callback was done without an exception, but parent has been changed since then - possible incorrect use of AppFuture? value is {}".format(executor_fu.result()))
                    raise ValueError("done callback called without an exception, but parent has been changed since then - possible incorrect use of AppFuture?")
                

            try:
                logger.debug("BENC: set_result path")
                res = executor_fu.result()
                if isinstance(res, RemoteException):
                    logger.debug("BENC: set_result RemoteException path - reraising")
                    res.reraise()
                super().set_result(executor_fu.result())

            except Exception as e:
                logger.debug("BENC: set_result - exception path, exception {}".format(e))
                if executor_fu.retries_left > 0:
                    # ignore this exception, because we'll assume some later parent executor
                    # will provide the answer
                    logger.debug("BENC: set_result - exception path but remaining retries - so not posting exception to AppFuture")
                else:
                    super().set_exception(e)

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

    @property
    def tid(self):
        return self._tid

    def update_parent(self, fut):
        """Add a callback to the parent to update the state.

        This handles the case where the user has called result on the AppFuture
        before the parent exists.
        """
        # with self._parent_update_lock:
        self.parent = fut
        fut.add_done_callback(self.parent_callback)
        self._parent_update_event.set()

    def cancel(self):
        if self.parent:
            return self.parent.cancel
        else:
            return False

    def cancelled(self):
        if self.parent:
            return self.parent.cancelled()
        else:
            return False

    def running(self):
        if self.parent:
            return self.parent.running()
        else:
            return False

    @property
    def outputs(self):
        return self._outputs

    def __repr__(self):
        if self.parent:
            with self.parent._condition:
                if self.parent._state == FINISHED:
                    if self.parent._exception:
                        return '<%s at %#x state=%s raised %s>' % (
                            self.__class__.__name__,
                            id(self),
                            _STATE_TO_DESCRIPTION_MAP[self.parent._state],
                            self.parent._exception.__class__.__name__)
                    else:
                        return '<%s at %#x state=%s returned %s>' % (
                            self.__class__.__name__,
                            id(self),
                            _STATE_TO_DESCRIPTION_MAP[self.parent._state],
                            self.parent._result.__class__.__name__)
                return '<%s at %#x state=%s>' % (
                    self.__class__.__name__,
                    id(self),
                    _STATE_TO_DESCRIPTION_MAP[self.parent._state])
        else:
            return '<%s at %#x state=%s>' % (
                self.__class__.__name__,
                id(self),
                _STATE_TO_DESCRIPTION_MAP[self._state])
