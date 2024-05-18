from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional
import datetime
import enum
import functools
import itertools

from memoization import cached
import spans

from linear_terminal_clock.constants import CHAR_EMPTY, CHAR_FULL, TERM
from linear_terminal_clock.cycle import Cycle
from linear_terminal_clock.types import BarOffset


@dataclass( eq = True, frozen = True )
class Bar( object ):
    """
    Defines the datetime meaning of each character in the bar during a specific
    cycle and for a specific length (number of characters).
    """
    cycle           : Cycle                             # Defines the span of time during which this Bar is valid
    slots           : tuple[spans.datetimerange,...]    # Stores the upper and lower datetime bounds of each character in this Bar
    slot_duration   : datetime.timedelta                # Time duration represented by a single slot / character


@cached
def bar_from_cycle_and_length( cycle: Cycle, bar_length: int ) -> Bar:
    """
    Bar constructor that automatically computes the contents of `.slots`
    from the datetime bounds in `cycle` and the number of slots indicated by
    `bar_length`.

    Memoized; if called more than once with identical arguements, returns a
    reference to the same instance every time.  Instantiation overhead is
    only incurred the first time this is called with new arguments.
    """

    # Determine the duration of one slot in seconds
    #   sec   bar    sec
    #   --- x ---- = ----
    #   bar   slot   slot
    seconds_per_bar  = ( cycle.end - cycle.start ).total_seconds()
    bars_per_slot    = 1.0 / bar_length  # force float division
    seconds_per_slot = seconds_per_bar * bars_per_slot

    return Bar(
        cycle = cycle,
        slots = tuple(
            spans.datetimerange(
                lower = cycle.start + datetime.timedelta( seconds = ( (i+0) * seconds_per_slot ) ),
                upper = cycle.start + datetime.timedelta( seconds = ( (i+1) * seconds_per_slot ) ),
                lower_inc = True,
                upper_inc = False,
            )
            for i in range( bar_length )
        ),
        slot_duration = datetime.timedelta( seconds = seconds_per_slot ),
    )


@enum.unique
class Phase( enum.Enum ):
    day         = 'day'
    night       = 'night'
    twilight    = 'twilight'


def gen_bar_chars( bar: Bar, dt_offset: BarOffset, time_label_text: Optional[str] = None ) -> Iterable[str]:
    """
    Yields all of the color codes and characters needed to render the bar.
    """

    # Compute this bar's sunset offset (we'll check it for every slot)
    sunset_offset = bar_offset_from_bar_and_datetime( bar, bar.cycle.sunset ) if bar.cycle.sunset else None

    # If caller wants a time label in the bar, compute the "time label offset" -
    # the x offset from the start of the bar of the leftmost character of
    # `time_label` - and associate it with the "time label text" by putting them
    # into a tuple (so typechecker is sure that both or neither exist).
    if time_label_text:
        if dt_offset < len( time_label_text ): time_label = ( time_label_text, BarOffset( 0                                      ) )
        else                                 : time_label = ( time_label_text, BarOffset( dt_offset - len( time_label_text ) + 1 ) )
    else                                     : time_label = None

    # For every slot in the bar, we need to yield the information needed to draw
    # the right thing in that slot
    for slot_offset, _ in enumerate( bar.slots ):

        # Compute this slot's `phase`
        if slot_offset == 0                     : phase = Phase.twilight    # Case: start of day
        elif sunset_offset:                                                 # Case: there's a sunset
            if   slot_offset <  sunset_offset   : phase = Phase.day
            elif slot_offset == sunset_offset   : phase = Phase.twilight
            else                                : phase = Phase.night
        elif not sunset_offset:                                             # Case: there's not a sunset
            if   bar.cycle.visible              : phase = Phase.day
            else                                : phase = Phase.night
        else                                    : raise ValueError( f"Couldn't choose a phase. {slot_offset=} | {sunset_offset=} | {bar.cycle.visible=}" )

        # Compute this slot's `text_char`, if it has one (a char that's part of the time label text)
        if time_label and ( 0 <= ( i := (slot_offset - time_label[1]) ) < len(time_label[0]) ): text_char = time_label[0][i]
        else                                                                                  : text_char = None

        # Compute whether the slot "has passed" (assuming `dt_offset` represents now)
        has_passed  = dt_offset >= slot_offset

        # Yield the color code
        if   phase == Phase.day      and     text_char and     has_passed: yield TERM.black_on_orange
        elif phase == Phase.day      and     text_char and not has_passed: yield TERM.orange
        elif phase == Phase.day      and not text_char and     has_passed: yield TERM.orange
        elif phase == Phase.day      and not text_char and not has_passed: yield TERM.orange
        elif phase == Phase.twilight and     text_char and     has_passed: yield TERM.black_on_purple
        elif phase == Phase.twilight and     text_char and not has_passed: yield TERM.purple
        elif phase == Phase.twilight and not text_char and     has_passed: yield TERM.purple
        elif phase == Phase.twilight and not text_char and not has_passed: yield TERM.purple
        elif phase == Phase.night    and     text_char and     has_passed: yield TERM.black_on_blue
        elif phase == Phase.night    and     text_char and not has_passed: yield TERM.blue
        elif phase == Phase.night    and not text_char and     has_passed: yield TERM.blue
        elif phase == Phase.night    and not text_char and not has_passed: yield TERM.blue
        else                                                    : raise ValueError( f"Couldn't choose a color. {phase=}, {text_char=}, {has_passed=}" )

        # Yield the character
        if   text_char  : yield text_char
        elif has_passed : yield CHAR_FULL
        else            : yield CHAR_EMPTY

        # If the char was a text char we must reset the term colors to "normal"
        # (text chars are frequently drawn with "not normal" background color
        # that must not persist into later chars)
        if text_char: yield TERM.normal


@cached
def render( bar: Bar, dt_offset: BarOffset, time_label_text: Optional[str] = None ) -> str:
    """
    Returns the bar rendered to a string that can be drawn to the terminal.
    """
    return ''.join( gen_bar_chars( bar, dt_offset, time_label_text ) )


@cached
def bar_offset_from_bar_and_datetime( bar: Bar, dt: datetime.datetime ) -> BarOffset:
    """
    Returns the number of bar chars required to represent `dt` (counting from
    the bar's start)
    """

    # Case: Datetime equals the upper limit of this bar.
    #
    # Cycles, Bars, and slots have inclusive lower bounds and exclusive upper
    # bounds. Although this datetime is technically part of the NEXT Bar (i.e.
    # it will be *included* in the first slot of the *next* Bar), it still makes
    # sense to return an offset for this Bar (rather than raise an error)
    # because it allows us to draw things at the end of this Bar.
    if dt == bar.cycle.end:
        return BarOffset( len( bar.slots ) )

    # Case: Datetime is included in one of this Bar's slots
    for i, slot in enumerate( bar.slots ):
        if dt in slot:
            return BarOffset( i )

    # Case: Datetime can't be represented as a meaningful offset for this Bar
    raise ValueError( f"To compute a `BarOffset` for {dt.isoformat()!r} it must either be in one of the Bar's slots or equal to the end of the Cycle | {bar.cycle=}" )


@cached
def bar_offset_from_bar_and_percent( bar: Bar, percentage: float ) -> BarOffset:
    """
    TODO add docstring
    """

    # Compute the number of percentage points in one bar char
    points_per_bar  = 100
    bars_per_char   = 1.0 / len(bar.slots)
    points_per_char = points_per_bar * bars_per_char

    # Compute the number of bar chars needed to represent the percentage
    chars = percentage / points_per_char

    # Return bar chars rounded to nearest int (not sure yet if better to CEIL, FLOOR, or ROUND)
    return BarOffset( int( chars + 0.5 ) )


@cached
def scale_from_bar( bar: Bar ) -> Optional[str]:
    """
    Return a string containing scale markers spaced out to match the specified
    bar length.  If such a string cannot be contructed, return None.
    """
    or_2_arity = lambda a, b: a or b                                            # need this because I can't find a built-in function version of Python's logical OR operator
    or_N_arity = lambda *args: functools.reduce( or_2_arity, args, None )       # with which to build a version of OR that can take more than 2 arguments

    # Return the scale with the smallest step that still has whitespace between the markers
    for step in ( 10, 20, 25, 33, 50 ):

        # Generate a string containing scale markers whose "number" spacing is
        # governed by `step` and whose "whitespace" spacing is governed by
        # `bar_len`.
        #
        # Sketch of algorithm:
        #   - We generate numerical values at `step` intervals using `range()`
        #     ("markers").
        #   - For each marker, we compute how far from the beginning of the bar
        #     it should be drawn (its "offset").
        #   - For each marker, we construct a list whose elements each represent
        #     a char of a "string" starting with "offset" whitespace chars
        #     followed by however many non-whitespace chars are needed to render
        #     the marker (Note: for a couple of reasons, we going to use `None`
        #     to represent the whitespace char).
        #   - We zip all of the marker lists together. Shorter lists are padded
        #     with `Nones` until they match the longest list. We end up with
        #     many tuples. Each corresponds to one char "position" along the
        #     bar, and each contains contains one char from every marker - the
        #     char that that marker's list wanted to draw at that position.
        #   - We choose which char to draw at each position by collapsing each
        #     tuple into a single char by running its elements through a
        #     "multi-OR" function.  If it contains any not-None chars, it
        #     collapses into one of them; if it contains only Nones, then it
        #     collapses into a None.
        #   - We join all of the chars into a string (replacing Nones with
        #     whitespace chars); this is a candidate scale marker string.
        candidate_scale = ''.join(
            c or ' '                                                            # take the "chars", converting `None`s into whitespace
            for c in itertools.starmap( or_N_arity, itertools.zip_longest( *(   # zip the lists into tuples, then collapse each tuple into a single "char" (scare quotes bc some of these are `None`)
                ([None]*offset) + list(str(marker))  # type: ignore             # construct a list like [None, None, None, '2', '5'] for an offset=3 and a marker=25
                for marker in range( 0, 100+1, step )                           # iterate over the percentage point markers for this step (the +1 gives us a closed range instead of a half-open one)
                for offset in ( bar_offset_from_bar_and_percent( bar, marker ), )        # compute the bar char offset needed by this marker
            ) ) )
        )

        # # DEBUG
        # print('', file=sys.stderr)
        # print(candidate_scale, file=sys.stderr)

        # Split the candidate scale on whitespace
        separated_markers = candidate_scale.split()

        # If the split results in the same number of markers as generating the
        # markers using range(), then this candidate scale has enough visual
        # separation between markers to be useable. Otherwise, we need to try
        # again with a larger step.
        if len(separated_markers) == len( range( 0, 100+1, step ) ):
            return candidate_scale
