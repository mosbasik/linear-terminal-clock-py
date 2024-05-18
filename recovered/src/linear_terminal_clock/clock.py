#!/usr/bin/env python

"""
Apologies in advance for the code style.  At $WORKPLACE we write Python in a
very... unsual style.  It's no PEP8 or Black (and isn't automatically enforced,
nor, indeed, automatically enforceable).  I used to hate it but now it comes out
of my fingers by itself.  I'm sorry.

The basic tenets are:
  1. wrap things with whitespace most of the time (there are exceptions)
  2. align things vertically if you can
  3. line length doesn't matter, within reason
  4. either all blocks in a scope get block level comments, or none do
"""

from __future__ import annotations

from typing import Optional
import datetime
import functools
import signal
import time

import tzlocal

from linear_terminal_clock.bar import bar_from_cycle_and_length, bar_offset_from_bar_and_datetime, scale_from_bar, render
from linear_terminal_clock.constants import CHAR_BEGIN, CHAR_END, LAT, LON, MARGIN_LR, TERM
from linear_terminal_clock.cycle import Cycle
import linear_terminal_clock.structlog_config

# Note: One approach to debugging a curses application is to open a second
# terminal and learn its terminal device by running `tty` (like `/dev/pts/18`).
# Then, `print()` logging statements to `file=sys.stderr`.  Then, run the
# application with its stderr redirected to that device by doing this:
# `2>/dev/pts/18`. Then the second terminal should show the logging statements.
# https://groups.google.com/g/comp.lang.python/c/e-4mT6s_Rmw/m/biZ0UN2wBQAJ



# Things I want to configure:
# labels
#   - rise
#     - label
#       - short (r)
#       - long (rise)
#       - time (05:56)
#       - custom
#     - marker
#       - custom
#   - set
#     - set
#     - [time]
#     - [just marker]
#     - [nothing]
#   - rise_next
#     - rise
#     - [time]
#     - [just marker]
#     - [nothing]
#   - now
#     - [time]




def main():
    """
    Entrypoint for normal use.
    """

    with TERM.fullscreen(), TERM.hidden_cursor(), TERM.cbreak():

        # Declare state variable to make it referenceable in the event loop
        cycle: Optional[Cycle] = None

        # Start the event loop
        while True:

            local_now = datetime.datetime.now().astimezone( tzlocal.get_localzone() )  # Look up local TZ inside event loop so we don't need to restart to pick up a change

            # If `cycle` isn't currently a Cycle spanning the current local
            # datetime, make it be that.
            #
            # (Motivation: avoid constructing a Cycle every frame.  Rather,
            # construct a Cycle once at launch and once thereafter every time the
            # old Cycle stops spanning the current local datetime.)
            if (
                   ( not cycle               )
                or ( local_now >= cycle.end  )
                or ( local_now < cycle.start )
            ):
                cycle = Cycle.spannning_dt( local_now, LAT, LON )

            # Draw the frame
            draw_frame( cycle, local_now )

            # Make it so resizing the window *immediately* redraws the frame
            register_redraw_on_resize( cycle, local_now )

            # Admire the frame for a while
            time.sleep( 5 )


def simulate_time():
    """
    Entrypoint for simulating the passage of time during debugging
    """

    with TERM.fullscreen(), TERM.hidden_cursor(), TERM.cbreak():

        # jan 20, 19:00 (1)
        # jun 20, 19:00 (6)
        # testing bounds
        STEP  = datetime.timedelta( minutes = 20 )
        START = datetime.datetime( 2022, 5, 12, 12,  0, tzinfo = tzlocal.get_localzone() )
        STOP  = datetime.datetime( 2022, 5, 14, 12,  0, tzinfo = tzlocal.get_localzone() )
        SLEEP = .5

        # faster pass through a few days including a DST boundary
        STEP  = datetime.timedelta( minutes = 5 )
        START = datetime.datetime( 2022, 3, 11, 12,  0, tzinfo = tzlocal.get_localzone() )
        STOP  = datetime.datetime( 2022, 3, 14, 12,  0, tzinfo = tzlocal.get_localzone() )
        SLEEP = .05

        # slower pass over the wraparound boundary
        STEP  = datetime.timedelta( seconds = 1 )
        START = datetime.datetime( 2022, 3, 12, 6,  25, tzinfo = tzlocal.get_localzone() )
        STOP  = datetime.datetime( 2022, 3, 12, 6,  50, tzinfo = tzlocal.get_localzone() )
        SLEEP = .025

        STEP  = datetime.timedelta( minutes = 120 )
        START = datetime.datetime( 2022,  7, 15, 12,   0, tzinfo = tzlocal.get_localzone() )
        STOP  = datetime.datetime( 2022, 12, 31, 23,  59, tzinfo = tzlocal.get_localzone() )
        SLEEP = .01

        # Declare state variable to make it referenceable in the event loop
        cycle: Optional[Cycle] = None

        # Start the debugging loop (used to reset the simulated time back to the start of the range forever)
        while True:
            # print( f'simulate_time(): Starting a new run of the test range from {START.isoformat()} to {STOP.isoformat()}', file = sys.stderr )

            # Set the simulated time to the start of the range
            local_now = START

            # Start the event loop (used to make the simulated time progress)
            while local_now <= STOP:
                if (
                       ( not cycle               )
                    or ( local_now >= cycle.end  )
                    or ( local_now < cycle.start )
                ):
                    # print( f'simulate_time(): Constructing new `Cycle` spanning {local_now.isoformat()}', file = sys.stderr )
                    cycle = Cycle.spannning_dt( local_now, LAT, LON )

                # Draw the frame
                draw_frame( cycle, local_now )

                # Make it so resizing the window *immediately* redraws the frame
                register_redraw_on_resize( cycle, local_now )

                # Admire the frame for a while
                time.sleep( SLEEP )

                # Pretend time is passing
                local_now += STEP


def register_redraw_on_resize( cycle: Cycle, dt: datetime.datetime ):
    """
    Register SIGWINCH handler that redraws the frame.

    The stdlib function `signal.signal()` is how to register the handler
    function to call upon getting a given signal (in our case, SIGWINCH -
    [sig]nal that the [win]dow [ch]anged).

    `signal()` expects a handler that takes two args - `signal` and `action`. We
    don't need to worry about what those are for. However, the handler is going
    to draw a frame, so it ALSO needs to know a `cycle` and `datetime`.

    So we define an anonymous four-arg function whose first two args are what's
    necessary to draw a frame and whose last two args are what's necessary to be
    a signal handler function.  When called, this function draws a frame.  Then
    we partially apply it by passing our cycle and datetime into it, which
    results in an anonymous two-arg function that we can pass to
    `signal.signal()`!

    https://blessed.readthedocs.io/en/latest/measuring.html#resizing
    """
    signal.signal( signal.SIGWINCH, functools.partial( lambda lcycle, ldt, lsignal, laction: draw_frame( lcycle, ldt ), cycle, dt ) )


def draw_frame( cycle: Cycle, now: datetime.datetime ) -> None:
    """
    TODO add docstring

    Sometimes there isn't a sunset in a given cycle. To quote James Wilson's
    project (https://jmw.name/projects/linear-clock/):

      There are places on Earth where, for some part of the year, the Sun never
      rises or sets!... [T]he solution I used was to mark the beginning and end
      of the day at the point where the Sun is closest to the horizon. This
      makes the solution continuous, in the sense that a person observing the
      clock while moving north into the Arctic circle at certain times of the
      year would see the day progress bar advance normally, while the sunset
      indicator would move toward either 0 or 100 before vanishing altogether.
    """

    # sunset = day_start + datetime.timedelta( minutes = 30 )
    # sunset = None

    # Clear the screen
    print( TERM.clear )

    #
    # Drawing the bar proper
    #

    # Compute some absolute coordinates
    cap_begin_x     = MARGIN_LR
    cap_end_x       = TERM.width - MARGIN_LR - 1
    bar_y           = TERM.height // 2
    bar_begin_x     = cap_begin_x + 1
    bar_end_x       = cap_end_x - 1

    # Draw the begin/end caps
    with TERM.location( cap_begin_x, bar_y ):
        print( CHAR_BEGIN )
    with TERM.location( cap_end_x, bar_y ):
        print( CHAR_END )

    # Draw the bar
    bar = bar_from_cycle_and_length( cycle, bar_end_x - bar_begin_x + 1 )
    with TERM.location( bar_begin_x, bar_y ):
        print( render( bar, bar_offset_from_bar_and_datetime( bar, now ), now.time().isoformat(timespec='minutes') ) )

    # Draw the scale markers, if there's enough space for them
    if ( scale := scale_from_bar( bar ) ):
        with TERM.location( bar_begin_x, bar_y + 1 ):
            print( scale )

    #
    # Drawing the markers
    #

    # If there is a sunset today
    if cycle.sunset:

        # Draw the sunset label
        sunset_offset = bar_offset_from_bar_and_datetime( bar, cycle.sunset )
        # draw_label( bar_begin_x, bar_y, sunset_offset, False, True, 'set' if sunset_offset > 4 else 's', '|' )
        draw_label( bar_begin_x, bar_y, sunset_offset, True, True, cycle.sunset.time().isoformat(timespec='minutes'), '|' )

        # Draw the sunrise label
        # draw_label( bar_begin_x, bar_y, bar_offset_from_bar_and_datetime( bar, cycle.start ), True, True, 'rise' if sunset_offset > 4 else 'r', '|' )
        draw_label( bar_begin_x, bar_y, bar_offset_from_bar_and_datetime( bar, cycle.start ), True, True, cycle.start.time().isoformat(timespec='minutes'), '|' )

        # Draw the NEXT sunrise label
        # draw_label( bar_begin_x, bar_y, bar_offset_from_bar_and_datetime( bar, cycle.end ), True, True, 'rise' if sunset_offset > 4 else 'r', '|' )
        draw_label( bar_begin_x, bar_y, bar_offset_from_bar_and_datetime( bar, cycle.end ), True, True, cycle.end.time().isoformat(timespec='minutes'), '|' )

    # Otherwise, there isn't a sunset today.
    else:

        assert isinstance( cycle.visible, bool )  # belt and suspenders

        # Draw the sun-closest-to-horizon marker
        draw_label( bar_begin_x, bar_y, bar_offset_from_bar_and_datetime( bar, cycle.start ), True if cycle.visible else False, True, 'darkest' if cycle.visible else 'lightest', '|' )

    # Draw any DEBUG strings
    text_begin_x = 0
    text_begin_y = 0
    # with term.location( text_begin_x, text_begin_y ):
    #     # print( f'{cycle.start.isoformat()=}, {sunset.isoformat()=}, {cycle.end.isoformat()=}' )
    #     print( f'     {cycle.start.isoformat()=}' )
    #     print( f'        {sunset.isoformat()=}' )
    #     print( f'{cycle.end.isoformat()=}' )
    #     print( f'           {now.isoformat()=}' )
    #     # print( f'{bar_len=}, {sunset_offset=}' )
    #     # print( f'{now.isoformat()=}, {sunset.isoformat()=}, {cycle.end.isoformat()=}' )


def draw_label(
    bar_begin_x : int,              # X coordinate of bar's beginning
    bar_y       : int,              # Y coordinate of bar
    offset      : int,              # X offset into the bar that the label is about
    above       : bool,             # True if the label goes above the bar; False if it goes below
    scale       : bool,             # True if a scale is being drawn; False if it isn't
    text        : Optional[str],    # Text of the label
    marker      : Optional[str],    # Marker showing precise location of label
) -> None:
    """
    """

    marker_y_offset = -1
    text_y_offset   = -2 if marker else -1

    if not above:
        marker_y_offset *= -1
        text_y_offset   *= -1

        if scale:
            marker_y_offset += 1
            text_y_offset   += 1

    if marker:
        assert len( marker ) == 1
        with TERM.location( bar_begin_x + offset, bar_y + marker_y_offset ):
            print( marker )

    if text:
        with TERM.location( bar_begin_x + offset - (len(text)//2), bar_y + text_y_offset ):
            print( text )


if  __name__ == '__main__':
    main()
