package com.resona.client

import java.util.concurrent.ConcurrentLinkedQueue

data class SpeakEvent(
    val text: String,
    val audioUrl: String?,
    val imageUrl: String?
)

object EventQueue {
    private val queue = ConcurrentLinkedQueue<SpeakEvent>()

    fun enqueue(event: SpeakEvent) {
        queue.add(event)
    }

    fun dequeue(): SpeakEvent? = queue.poll()

    fun isEmpty(): Boolean = queue.isEmpty()
}
