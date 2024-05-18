import os
import pathlib
import sys
import structlog


# ------------------------------------------------------------------------------
# Custom Processors
# ------------------------------------------------------------------------------

# Relevant:
#   - https://www.structlog.org/en/stable/processors.html

def process_erase_undiffable_context( wrapped_logger: structlog.typing.WrappedLogger, method_name: str, event_dict: structlog.typing.EventDict ) -> structlog.typing.EventDict:
    """
    Removes values from the event dict that will always be different from one
    run to the next and therefore pollute attempts at diffing logs from
    different runs against each other.

    Intended to be something that's enabled on a local developer machine - not
    something that's ever enabled in production.
    """
    event_dict.pop( 'lineno'          , '' )
    event_dict.pop( 'process'         , '' )
    event_dict.pop( 'thread'          , '' )
    event_dict.pop( 'timestamp'       , '' )
    return event_dict


def process_event_length_warning( wrapped_logger: structlog.typing.WrappedLogger, method_name: str, event_dict: structlog.typing.EventDict ) -> structlog.typing.EventDict:
    """
    It's easier to read the human-readable log format when event strings are
    fairly short and vertically aligned.  To accomplish this, we recommend that
    event strings be kept to 40 chars or less.

    It's not an error for an event string to be longer, but this processor
    annotates logs with long event strings to inform devs of the recommendation
    and to make it easy to find and fix cases by scanning our logs later.
    """
    event_length_limit = 40
    if ( length := len(event_dict['event']) ) > event_length_limit:
        event_dict['event_length']          = length
        event_dict['event_length_warning']  = f'Event surpasses recommended length of {event_length_limit} chars'
    return event_dict


# ------------------------------------------------------------------------------
# Custom Renderers
# ------------------------------------------------------------------------------

# Relevant:
#   - https://www.structlog.org/en/stable/processors.html#adapting

class HumanConsoleRenderer( structlog.dev.ConsoleRenderer ):
    """
    Adds `filename_lineno` (for humans to read), drops `filename` and `lineno`
    (used to build it, so now redundant), then renders with a normal
    ConsoleRenderer.
    """

    def __call__( self, wrapped_logger: structlog.typing.WrappedLogger, method_name: str, event_dict: structlog.typing.EventDict ) -> str | bytes:

        match event_dict.pop( 'filename', None ), event_dict.pop( 'lineno', None ):
            case str() as filename, int() as lineno: event_dict[ 'filename_lineno' ] = f'{filename}:{lineno}'   # most common case
            case str() as filename, None  as lineno: event_dict[ 'filename_lineno' ] = f'{filename}:xx'         # the line numbers have probably been omitted to make diffing easier
            case None  as filename, None  as lineno: pass                                                       # super minimal; don't add a key

        # Then just return the results of running a normal ConsoleRenderer
        return super().__call__( logger = wrapped_logger, name = method_name, event_dict = event_dict )


# ------------------------------------------------------------------------------
# Choose which destination to use based on STRUCTLOG_DESTINATION
# ------------------------------------------------------------------------------

match ( STRUCTLOG_DESTINATION := os.environ.get( 'STRUCTLOG_DESTINATION', 'STDOUT' ) ):  # When env var is not specified, route logs to stdout
    case 'STDERR'           : destination = structlog.PrintLoggerFactory( file = sys.stderr )  # Magic string that route logs to stderr
    case 'STDOUT'           : destination = structlog.PrintLoggerFactory( file = sys.stdout )  # Magic string that route logs to stdout
    case _ as provided_path : destination = structlog.PrintLoggerFactory( file = open( pathlib.Path( provided_path ), mode = 'a' ) )  # Assume every other value is a file path; route logs there



structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper( fmt = 'iso', utc = True, key = 'timestamp' ),  # Example: "2024-05-09T19:07:26.769326Z".  Fight me (Peter Henry) if you want to deploy code anywhere that's logging in non-UTC (but do whatever you like locally!)
        structlog.processors.CallsiteParameterAdder( parameters = [
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.LINENO,
            structlog.processors.CallsiteParameter.FUNC_NAME,
            structlog.processors.CallsiteParameter.THREAD,
            structlog.processors.CallsiteParameter.THREAD_NAME,
        ] ),
        # process_erase_undiffable_context,  # Keep disabled in production. Enable during development if you want to diff the logs of two runs to see what changed.
        process_event_length_warning,
        HumanConsoleRenderer(
            columns = [
                structlog.dev.Column( 'timestamp'       , structlog.dev.KeyValueColumnFormatter( key_style=None, value_style='', reset_style='', value_repr=str, width=0, prefix='', postfix='' ) ),
                structlog.dev.Column( 'level'           , structlog.dev.KeyValueColumnFormatter( key_style=None, value_style='', reset_style='', value_repr=str, width=8, prefix='', postfix='' ) ),
                # structlog.dev.Column( 'thread_name'     , structlog.dev.KeyValueColumnFormatter( key_style=None, value_style='', reset_style='', value_repr=str, width=25, prefix='', postfix='' ) ),
                structlog.dev.Column( 'filename_lineno' , structlog.dev.KeyValueColumnFormatter( key_style=None, value_style='', reset_style='', value_repr=str, width=40, prefix='', postfix='' ) ),
                structlog.dev.Column( 'func_name'       , structlog.dev.KeyValueColumnFormatter( key_style=None, value_style='', reset_style='', value_repr=str, width=40, prefix='', postfix='' ) ),
                structlog.dev.Column( 'event'           , structlog.dev.KeyValueColumnFormatter( key_style=None, value_style='', reset_style='', value_repr=str, width=40, prefix='', postfix=' |' ) ),
                structlog.dev.Column( ''                , structlog.dev.KeyValueColumnFormatter( key_style=''  , value_style='', reset_style='', value_repr=str, width=0, prefix='', postfix='' ) ),
            ],
        ),
    ],
    logger_factory = destination,
    cache_logger_on_first_use = True,
)


# ------------------------------------------------------------------------------
# Use newly-configured logger to report that configuring the logger is done :)
# ------------------------------------------------------------------------------

logger = structlog.get_logger()
logger = logger.bind( STRUCTLOG_DESTINATION = STRUCTLOG_DESTINATION )
# logger = logger.bind( STRUCTLOG_RENDERER = STRUCTLOG_RENDERER )

logger.debug( 'Configured structlog' )
