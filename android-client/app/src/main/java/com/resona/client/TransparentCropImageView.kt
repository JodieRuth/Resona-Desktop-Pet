package com.resona.client

import android.content.Context
import android.graphics.Bitmap
import android.util.AttributeSet
import androidx.appcompat.widget.AppCompatImageView

class TransparentCropImageView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : AppCompatImageView(context, attrs) {

    fun setBitmapWithCrop(source: Bitmap) {
        val cropped = cropTransparent(source)
        setImageBitmap(cropped)
    }

    private fun cropTransparent(bitmap: Bitmap): Bitmap {
        val width = bitmap.width
        val height = bitmap.height
        var minX = width
        var minY = height
        var maxX = -1
        var maxY = -1
        val pixels = IntArray(width * height)
        bitmap.getPixels(pixels, 0, width, 0, 0, width, height)
        for (y in 0 until height) {
            val rowStart = y * width
            for (x in 0 until width) {
                val alpha = pixels[rowStart + x] ushr 24
                if (alpha > 0) {
                    if (x < minX) minX = x
                    if (y < minY) minY = y
                    if (x > maxX) maxX = x
                    if (y > maxY) maxY = y
                }
            }
        }
        if (maxX < minX || maxY < minY) {
            return bitmap
        }
        val cropWidth = maxX - minX + 1
        val cropHeight = maxY - minY + 1
        return Bitmap.createBitmap(bitmap, minX, minY, cropWidth, cropHeight)
    }
}
