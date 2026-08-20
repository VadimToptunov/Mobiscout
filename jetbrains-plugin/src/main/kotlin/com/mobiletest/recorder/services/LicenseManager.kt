package com.mobiletest.recorder.services

import com.intellij.ui.LicensingFacade

/**
 * PRO-licence gate for the plugin — scaffolding for the future Freemium listing.
 *
 * Mobiscout ships today as a **free** Marketplace plugin, so [FREEMIUM_ENABLED] is
 * `false` and [isPro] always returns `false` (nothing in the UI is gated yet). When
 * the paid tier launches:
 *   1. become a verified JetBrains vendor and obtain the real [PRODUCT_CODE];
 *   2. add a `<product-descriptor code="..." release-date="..." release-version="..."
 *      optional="true"/>` to plugin.xml (the `optional=true` marks it Freemium);
 *   3. flip [FREEMIUM_ENABLED] to `true`.
 *
 * Then [isPro] reflects the JetBrains-managed licence via [LicensingFacade], and the
 * plugin can gate PRO-only affordances (and tell the engine to run the PRO tier).
 *
 * Keeping the check here — behind one flag, off by default — means the Freemium flip
 * is a small, reviewable change rather than a scattered retrofit.
 */
object LicenseManager {

    /** Freemium is not live yet; the plugin is a free listing. See the class doc. */
    private const val FREEMIUM_ENABLED = false

    /** Placeholder — JetBrains issues the real product code during paid onboarding. */
    private const val PRODUCT_CODE = "PMOBISCOUT"

    /**
     * Whether the current user holds a valid PRO licence.
     *
     * Always `false` while Freemium is disabled (everything is free). When enabled it
     * checks the JetBrains-managed licence: a non-null confirmation stamp for
     * [PRODUCT_CODE] means the user is licensed (a paid or active trial licence).
     */
    fun isPro(): Boolean {
        if (!FREEMIUM_ENABLED) return false
        val facade = LicensingFacade.getInstance() ?: return false
        return facade.getConfirmationStamp(PRODUCT_CODE) != null
    }
}
