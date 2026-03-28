package com.escalada.judgeremote

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.Intent.EXTRA_TEXT
import android.graphics.Bitmap
import android.os.Bundle
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.edit
import com.escalada.judgeremote.databinding.ActivityMainBinding
import org.json.JSONObject
import kotlin.math.abs

@Suppress("SpellCheckingInspection")
class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
    private var pageReady = false
    private val pullRefreshThresholdPx by lazy { 96f * resources.displayMetrics.density }
    private val tapSlopPx by lazy { ViewConfiguration.get(this).scaledTouchSlop.toFloat() }
    private var pullTracking = false
    private var pullTriggered = false
    private var pullStartX = 0f
    private var pullStartY = 0f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        window.addFlags(FLAG_KEEP_SCREEN_ON)
        setupWebView()
        setupPullToRefresh()
        setupBackHandling()
        seedInitialUrl()
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (handleJudgeVolumeKey(event)) {
            return true
        }
        return super.dispatchKeyEvent(event)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onDestroy() {
        binding.webView.apply {
            stopLoading()
            clearHistory()
            removeAllViews()
            destroy()
        }
        super.onDestroy()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(binding.webView, true)

        binding.webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = false
            displayZoomControls = false
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            userAgentString = "$userAgentString EscaladaJudgeRemoteAndroid/1.0"
        }

        binding.webView.isFocusable = true
        binding.webView.isFocusableInTouchMode = true
        binding.webView.webChromeClient = WebChromeClient()
        binding.webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                pageReady = false
                binding.progressBar.visibility = View.VISIBLE
                updateStatus(getString(R.string.status_loading))
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                pageReady = true
                binding.progressBar.visibility = View.GONE
                if (!url.isNullOrBlank()) {
                    prefs.edit {
                        putString(PREF_LAST_URL, url)
                    }
                }
                updateStatus(getString(R.string.status_ready))
            }

            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?,
            ): Boolean = false

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                if (request?.isForMainFrame == true) {
                    pageReady = false
                    binding.progressBar.visibility = View.GONE
                    updateStatus(
                        getString(
                            R.string.status_error,
                            error?.description?.toString() ?: getString(R.string.status_error_unknown),
                        ),
                    )
                }
            }
        }
    }

    private fun setupPullToRefresh() {
        binding.webView.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    pullTracking = binding.webView.scrollY == 0
                    pullTriggered = false
                    pullStartX = event.x
                    pullStartY = event.y
                }

                MotionEvent.ACTION_MOVE -> {
                    if (
                        pullTracking &&
                        !pullTriggered &&
                        binding.webView.scrollY == 0 &&
                        event.y - pullStartY >= pullRefreshThresholdPx
                    ) {
                        pullTriggered = true
                        if (!binding.webView.url.isNullOrBlank()) {
                            binding.webView.reload()
                        }
                    }
                }

                MotionEvent.ACTION_UP,
                MotionEvent.ACTION_CANCEL,
                -> {
                    if (
                        event.actionMasked == MotionEvent.ACTION_UP &&
                        !pullTriggered &&
                        abs(event.x - pullStartX) <= tapSlopPx &&
                        abs(event.y - pullStartY) <= tapSlopPx
                    ) {
                        view.performClick()
                    }
                    pullTracking = false
                    pullTriggered = false
                }
            }
            false
        }
    }

    private fun setupBackHandling() {
        onBackPressedDispatcher.addCallback(this) {
            if (binding.webView.canGoBack()) {
                binding.webView.goBack()
            } else {
                finish()
            }
        }
    }

    private fun seedInitialUrl() {
        val hasExplicitLaunchUrl = intent?.hasExtra(EXTRA_JUDGE_URL) == true
        val initial =
            if (hasExplicitLaunchUrl) {
                normalizeUrl(intent?.getStringExtra(EXTRA_JUDGE_URL).orEmpty())
            } else {
                extractLegacyLaunchUrl() ?: normalizeUrl(prefs.getString(PREF_LAST_URL, "").orEmpty())
            }

        if (initial != null) {
            loadJudgeUrl(initial)
        } else {
            redirectToWelcome()
        }
    }

    private fun extractLegacyLaunchUrl(): String? {
        val dataUrl = normalizeUrl(intent?.dataString.orEmpty())
        if (dataUrl != null) return dataUrl

        val sharedTextUrl = normalizeUrl(intent?.getStringExtra(EXTRA_TEXT).orEmpty())
        if (sharedTextUrl != null) return sharedTextUrl

        return null
    }

    private fun loadJudgeUrl(rawUrl: String) {
        val normalized = normalizeUrl(rawUrl)
        if (normalized == null) {
            redirectToWelcome()
            return
        }

        pageReady = false
        prefs.edit {
            putString(PREF_LAST_URL, normalized)
        }
        binding.webView.loadUrl(normalized)
    }

    private fun redirectToWelcome() {
        Toast.makeText(this, R.string.toast_no_judge_url_selected, Toast.LENGTH_SHORT).show()
        startActivity(Intent(this, WelcomeActivity::class.java))
        finish()
    }

    private fun handleJudgeVolumeKey(event: KeyEvent): Boolean {
        val key = when (event.keyCode) {
            KeyEvent.KEYCODE_VOLUME_UP -> SHORTCUT_HALF_HOLD
            KeyEvent.KEYCODE_VOLUME_DOWN -> SHORTCUT_HOLD
            else -> return false
        }

        if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
            dispatchShortcutToPage(key)
        }
        return true
    }

    private fun dispatchShortcutToPage(key: String) {
        if (!pageReady) {
            Toast.makeText(this, R.string.toast_page_not_ready, Toast.LENGTH_SHORT).show()
            return
        }

        val quotedKey = JSONObject.quote(key)
        val script =
            """
            (() => {
              const event = new KeyboardEvent('keydown', {
                key: $quotedKey,
                bubbles: true,
                cancelable: true
              });
              window.dispatchEvent(event);
            })();
            """.trimIndent()

        binding.webView.evaluateJavascript(script, null)
        val statusRes =
            if (key == SHORTCUT_HALF_HOLD) {
                R.string.status_sent_half_hold
            } else {
                R.string.status_sent_hold
            }
        updateStatus(getString(statusRes))
    }

    private fun updateStatus(text: String) {
        binding.statusText.text = text
    }

    companion object {
        private const val SHORTCUT_HALF_HOLD = "AudioVolumeUp"
        private const val SHORTCUT_HOLD = "AudioVolumeDown"
    }
}
