package com.brahma.connect.camera

import android.content.Context
import android.graphics.Bitmap
import android.util.Base64
import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors

/**
 * CameraVisionStreamer
 * Manages CameraX preview and background frame sampling for JARVIS live multimodal vision.
 * Streams downscaled JPEG frames at ~1 frame per 1.2s to preserve network bandwidth.
 */
class CameraVisionStreamer(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val onFrameCaptured: (base64Jpeg: String) -> Unit,
) {
    companion object {
        private const val TAG = "CameraVisionStreamer"
        private const val TARGET_MAX_DIMENSION = 640
        private const val FRAME_INTERVAL_MS = 1200L
    }

    private var cameraProvider: ProcessCameraProvider? = null
    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private var lastFrameTime = 0L
    private var lensFacing = CameraSelector.LENS_FACING_BACK
    private var previewView: PreviewView? = null
    private var isStreaming = false

    fun start(preview: PreviewView? = null) {
        this.previewView = preview
        val providerFuture = ProcessCameraProvider.getInstance(context)
        providerFuture.addListener({
            try {
                cameraProvider = providerFuture.get()
                bindCameraUseCases()
                isStreaming = true
                Log.i(TAG, "Camera vision streaming started.")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start camera streaming: ${e.message}", e)
            }
        }, ContextCompat.getMainExecutor(context))
    }

    fun switchCamera() {
        lensFacing = if (lensFacing == CameraSelector.LENS_FACING_BACK) {
            CameraSelector.LENS_FACING_FRONT
        } else {
            CameraSelector.LENS_FACING_BACK
        }
        if (isStreaming) {
            bindCameraUseCases()
        }
    }

    fun isUsingFrontCamera(): Boolean = lensFacing == CameraSelector.LENS_FACING_FRONT

    fun stop() {
        isStreaming = false
        try {
            cameraProvider?.unbindAll()
            Log.i(TAG, "Camera vision streaming stopped.")
        } catch (e: Exception) {
            Log.w(TAG, "Error stopping camera: ${e.message}")
        }
    }

    private fun bindCameraUseCases() {
        val provider = cameraProvider ?: return
        provider.unbindAll()

        val cameraSelector = CameraSelector.Builder()
            .requireLensFacing(lensFacing)
            .build()

        // 1. Viewfinder Preview (if PreviewView provided)
        val previewUseCase = Preview.Builder().build().also {
            previewView?.let { pv ->
                it.setSurfaceProvider(pv.surfaceProvider)
            }
        }

        // 2. Image Analysis for Gemini Vision
        val imageAnalysis = ImageAnalysis.Builder()
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
            .build()

        imageAnalysis.setAnalyzer(analysisExecutor) { imageProxy ->
            val now = System.currentTimeMillis()
            if (now - lastFrameTime < FRAME_INTERVAL_MS) {
                imageProxy.close()
                return@setAnalyzer
            }
            lastFrameTime = now

            try {
                // Convert ImageProxy to Bitmap using CameraX built-in method
                val originalBitmap = imageProxy.toBitmap()

                // Downscale for network efficiency
                val scaledBitmap = scaleBitmapDown(originalBitmap, TARGET_MAX_DIMENSION)

                // Compress to JPEG
                val outputStream = ByteArrayOutputStream()
                scaledBitmap.compress(Bitmap.CompressFormat.JPEG, 75, outputStream)
                val jpegBytes = outputStream.toByteArray()

                // Encode Base64
                val base64Jpeg = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
                onFrameCaptured(base64Jpeg)
            } catch (e: Exception) {
                Log.w(TAG, "Error analyzing camera frame: ${e.message}")
            } finally {
                imageProxy.close()
            }
        }

        try {
            provider.bindToLifecycle(lifecycleOwner, cameraSelector, previewUseCase, imageAnalysis)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to bind camera use cases: ${e.message}", e)
        }
    }

    private fun scaleBitmapDown(bitmap: Bitmap, maxDimension: Int): Bitmap {
        val width = bitmap.width
        val height = bitmap.height
        if (width <= maxDimension && height <= maxDimension) {
            return bitmap
        }
        val ratio = width.toFloat() / height.toFloat()
        val newWidth: Int
        val newHeight: Int
        if (width > height) {
            newWidth = maxDimension
            newHeight = (maxDimension / ratio).toInt()
        } else {
            newHeight = maxDimension
            newWidth = (maxDimension * ratio).toInt()
        }
        return Bitmap.createScaledBitmap(bitmap, newWidth, newHeight, true)
    }
}
