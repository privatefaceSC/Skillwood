package io.skillwood.client

sealed class Result<out T> {
    data class Success<T>(val value: T) : Result<T>()
    data class Error(val message: String, val kind: ErrorKind) : Result<Nothing>()

    enum class ErrorKind { Network, Unauthorized, NotFound, BadRequest, Server, Unknown }
}
