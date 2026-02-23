package com.resona.client

import java.io.File
import java.io.FileOutputStream

object WavWriter {
    fun writeWav(file: File, pcmData: ByteArray, sampleRate: Int) {
        FileOutputStream(file).use { out ->
            val totalDataLen = pcmData.size + 36
            val byteRate = sampleRate * 2
            out.write("RIFF".toByteArray(Charsets.US_ASCII))
            out.write(intToLittleEndian(totalDataLen))
            out.write("WAVE".toByteArray(Charsets.US_ASCII))
            out.write("fmt ".toByteArray(Charsets.US_ASCII))
            out.write(intToLittleEndian(16))
            out.write(shortToLittleEndian(1.toShort()))
            out.write(shortToLittleEndian(1.toShort()))
            out.write(intToLittleEndian(sampleRate))
            out.write(intToLittleEndian(byteRate))
            out.write(shortToLittleEndian(2.toShort()))
            out.write(shortToLittleEndian(16.toShort()))
            out.write("data".toByteArray(Charsets.US_ASCII))
            out.write(intToLittleEndian(pcmData.size))
            out.write(pcmData)
        }
    }

    private fun intToLittleEndian(value: Int): ByteArray {
        return byteArrayOf(
            (value and 0xff).toByte(),
            ((value shr 8) and 0xff).toByte(),
            ((value shr 16) and 0xff).toByte(),
            ((value shr 24) and 0xff).toByte()
        )
    }

    private fun shortToLittleEndian(value: Short): ByteArray {
        return byteArrayOf(
            (value.toInt() and 0xff).toByte(),
            ((value.toInt() shr 8) and 0xff).toByte()
        )
    }
}
