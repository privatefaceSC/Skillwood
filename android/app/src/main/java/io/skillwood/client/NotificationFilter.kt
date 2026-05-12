package io.skillwood.client

/** Чистая логика: пересылать ли уведомление от данного пакета. */
object NotificationFilter {

    fun shouldForward(
        packageName: String,
        ownPackage: String,
        allowed: Set<String>,
    ): Boolean {
        if (packageName == ownPackage) return false
        return packageName in allowed
    }
}
