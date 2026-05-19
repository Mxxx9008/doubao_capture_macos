// SSL Pinning Bypass for Doubao - v2 (no dex file write)
setTimeout(function() {
    Java.perform(function() {
        console.log("[*] SSL Pinning Bypass v2 - Starting...");

        // Hook SSLContext.init to inject all-trusting TrustManager
        var SSLContext = Java.use('javax.net.ssl.SSLContext');
        var TrustManager = Java.use('javax.net.ssl.X509TrustManager');

        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, endpoint) {
            console.log("[*] verifyChain bypassed for: " + host);
            return untrustedChain;
        };

        // Hook TrustManagerImpl.checkTrusted
        try {
            TrustManagerImpl.checkTrusted.implementation = function(chain, authType, session, host) {
                console.log("[*] checkTrusted bypassed for: " + host);
                return;
            };
        } catch(e) {
            console.log("[*] checkTrusted hook skipped: " + e);
        }

        // Bypass OkHttp CertificatePinner
        try {
            var CertificatePinner = Java.use('okhttp3.CertificatePinner');
            CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, peerCertificates) {
                console.log("[*] OkHttp pinning bypassed: " + hostname);
                return;
            };
        } catch(e) {
            console.log("[*] OkHttp CertificatePinner not found (expected)");
        }

        // Also try to hook javax.net.ssl.HttpsURLConnection
        try {
            var HttpsURLConnection = Java.use('javax.net.ssl.HttpsURLConnection');
            HttpsURLConnection.setDefaultHostnameVerifier.implementation = function(hv) {
                console.log("[*] DefaultHostnameVerifier bypassed");
                return;
            };
        } catch(e) {
            console.log("[*] HttpsURLConnection hook skipped");
        }

        console.log("[*] SSL Pinning Bypass v2 - Complete!");
    });
}, 0);
