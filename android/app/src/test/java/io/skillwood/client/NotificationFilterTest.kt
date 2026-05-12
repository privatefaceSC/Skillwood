package io.skillwood.client

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationFilterTest {

    private val own = "io.skillwood.client"

    @Test
    fun own_package_is_rejected_even_if_allowed() {
        assertFalse(NotificationFilter.shouldForward(own, own, setOf(own)))
    }

    @Test
    fun unknown_package_is_rejected() {
        assertFalse(NotificationFilter.shouldForward("com.foo", own, setOf("org.telegram.messenger")))
    }

    @Test
    fun allowed_package_passes() {
        assertTrue(NotificationFilter.shouldForward(
            "org.telegram.messenger", own, setOf("org.telegram.messenger")))
    }

    @Test
    fun empty_allowed_set_rejects_everything() {
        assertFalse(NotificationFilter.shouldForward("org.telegram.messenger", own, emptySet()))
        assertFalse(NotificationFilter.shouldForward("com.anything.else", own, emptySet()))
    }

    @Test
    fun multiple_allowed_packages_all_pass() {
        val allowed = setOf("org.telegram.messenger", "ru.oneme.app")
        assertTrue(NotificationFilter.shouldForward("org.telegram.messenger", own, allowed))
        assertTrue(NotificationFilter.shouldForward("ru.oneme.app", own, allowed))
        assertFalse(NotificationFilter.shouldForward("com.whatsapp", own, allowed))
    }
}
