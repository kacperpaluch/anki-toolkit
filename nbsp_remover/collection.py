# -*- coding: utf-8 -*-
# 2022 - Matthias M. | @kleinerpirat

from aqt import mw
from aqt.operations.note import find_and_replace

from .utils import (
    purge_tooltip, _get_skip_field,
    NBSP, DIV_TAG_RE, DIV_WRAP_RE, TRAILING_BR_RE,
)


def clean_collection() -> None:
    skip_field = _get_skip_field()

    field_names = set()
    for model in mw.col.models.all():
        for field in model['flds']:
            field_names.add(field['name'])

    field_names.discard(skip_field)

    div_br_ops = []
    cleanup_ops = []
    for field_name in field_names:
        op = find_and_replace(
            parent=mw,
            note_ids=[],
            search=DIV_WRAP_RE,
            replacement=r"$1<br>",
            regex=True,
            field_name=field_name,
            match_case=True,
        )
        div_br_ops.append(op)

        cleanup_op = find_and_replace(
            parent=mw,
            note_ids=[],
            search=TRAILING_BR_RE,
            replacement="",
            regex=True,
            field_name=field_name,
            match_case=True,
        )
        cleanup_ops.append(cleanup_op)

    nbsp_count = 0
    div_count = 0
    div_br_count = 0
    operations_remaining = 0

    def show_tooltip():
        purge_tooltip(mw, nbsp_count, div_count, div_br_count)

    def run_cleanup_phase():
        nonlocal operations_remaining
        operations_remaining = len(cleanup_ops)
        if operations_remaining == 0:
            show_tooltip()
            return

        def on_done(out_or_err):
            nonlocal operations_remaining
            operations_remaining -= 1
            if operations_remaining <= 0:
                show_tooltip()

        for cleanup_op in cleanup_ops:
            cleanup_op.success(on_done)
            cleanup_op.failure(on_done)
            cleanup_op.run_in_background()

    def run_div_br_phase():
        nonlocal operations_remaining
        operations_remaining = len(div_br_ops)
        if operations_remaining == 0:
            run_cleanup_phase()
            return

        def on_success(out):
            nonlocal div_br_count, operations_remaining
            div_br_count += out.count
            operations_remaining -= 1
            if operations_remaining <= 0:
                run_cleanup_phase()

        def on_fail(err):
            nonlocal operations_remaining
            operations_remaining -= 1
            if operations_remaining <= 0:
                run_cleanup_phase()

        for op in div_br_ops:
            op.success(on_success)
            op.failure(on_fail)
            op.run_in_background()

    def track_div(out):
        nonlocal div_count
        div_count += out.count
        run_div_br_phase()

    def track_div_fail(err):
        run_div_br_phase()

    def track_nbsp(out):
        nonlocal nbsp_count
        nbsp_count = out.count
        op2.run_in_background()

    def track_nbsp_fail(err):
        op2.run_in_background()

    op1 = find_and_replace(
        parent=mw, note_ids=[], search=NBSP, replacement=" ",
        regex=False, field_name=None, match_case=True,
    )
    op2 = find_and_replace(
        parent=mw, note_ids=[], search=DIV_TAG_RE, replacement="",
        regex=True, field_name=skip_field, match_case=True,
    )

    op1.success(track_nbsp)
    op1.failure(track_nbsp_fail)
    op2.success(track_div)
    op2.failure(track_div_fail)

    op1.run_in_background()
