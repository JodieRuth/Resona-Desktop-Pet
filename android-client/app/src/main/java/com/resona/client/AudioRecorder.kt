package com.resona.client

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import java.io.ByteArrayOutputStream
import java.io.File
import kotlin.math.abs

class AudioRecorder(
    private val sampleRate: Int,
    private val maxDurationSec: Double,
    private val silenceSec: Double,
    private val onComplete: (File) -> Unit,
    private val onError: (String) -> Unit
) {
    private var recording = false
    private var recordThread: Thread? = null

    fun start(outputFile: File) {
        if (recording) return
        recording = true
        recordThread = Thread {
            val bufferSize = AudioRecord.getMinBufferSize(
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )
            if (bufferSize <= 0) {
                recording = false
                onError("录音初始化失败")
                return@Thread
            }
            val audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(bufferSize)
            val maxFrames = (maxDurationSec * sampleRate / (bufferSize / 2)).toInt()
            var frames = 0
            var silenceFrames = 0
            val silenceLimitFrames = (silenceSec * sampleRate / (bufferSize / 2)).toInt().coerceAtLeast(1)
            val minFrames = (2.0 * sampleRate / (bufferSize / 2)).toInt().coerceAtLeast(1)
            val volumeThreshold = 600
            try {
                audioRecord.startRecording()
                while (recording && frames < maxFrames) {
                    val read = audioRecord.read(buffer, 0, buffer.size)
                    if (read > 0) {
                        output.write(buffer, 0, read)
                        val avg = averageVolume(buffer, read)
                        if (avg < volumeThreshold) {
                            silenceFrames += 1
                            if (frames > minFrames && silenceFrames >= silenceLimitFrames) {
                                break
                            }
                        } else {
                            silenceFrames = 0
                        }
                        frames += 1
                    }
                }
                audioRecord.stop()
                audioRecord.release()
                val pcm = output.toByteArray()
                WavWriter.writeWav(outputFile, pcm, sampleRate)
                recording = false
                onComplete(outputFile)
            } catch (e: Exception) {
                try {
                    audioRecord.stop()
                } catch (_: Exception) {
                }
                audioRecord.release()
                recording = false
                onError(e.message ?: "录音失败")
            }
        }
        recordThread?.start()
    }

    fun stop() {
        recording = false
    }

    private fun averageVolume(buffer: ByteArray, size: Int): Int {
        var sum = 0
        var count = 0
        var i = 0
        while (i + 1 < size) {
            val sample = (buffer[i + 1].toInt() shl 8) or (buffer[i].toInt() and 0xff)
            sum += abs(sample)
            count++
            i += 2
        }
        return if (count == 0) 0 else sum / count
    }
}
