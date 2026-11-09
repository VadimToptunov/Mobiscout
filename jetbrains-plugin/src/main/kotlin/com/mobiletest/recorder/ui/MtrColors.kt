package com.mobiletest.recorder.ui

import com.intellij.ui.JBColor

/**
 * The plugin's status colours in one place, so "ready / idle / not-ready" read the same across
 * the tool-window status dot, the Devices table and the panels. Each is a theme-aware [JBColor]
 * (a hardcoded Color washes out in Darcula) — previously the same hex pairs were copied at every
 * call site, which let the shades (and the semantics) drift.
 */
object MtrColors {
    /** Ready: a running engine, or a booted / online device. */
    val ready = JBColor(0x2E7D32, 0x6A8759)

    /** Idle / stopped / unknown. */
    val idle = JBColor(0x9E9E9E, 0x808080)

    /** Connected but not ready (an offline / unauthorized device). */
    val notReady = JBColor(0xB8860B, 0xBF8B00)
}
