// Hook Cronet/ttnet Java layer - v6: hook onReadCompleted (private) for PLAINTEXT!
setTimeout(function() {
    Java.perform(function() {
        console.log("[*] Cronet Java hook v6 - targeting onReadCompleted...");

        // HOOK 1: CronetBidirectionalStream.onReadCompleted(ByteBuffer,int,int,int,long)
        // This is THE method that receives SSE streaming response data
        try {
            var CronetBidirectionalStream = Java.use('com.ttnet.org.chromium.net.impl.CronetBidirectionalStream');

            // All methods including private ones
            var methods = CronetBidirectionalStream.class.getDeclaredMethods();
            for (var i = 0; i < methods.length; i++) {
                var m = methods[i];
                m.setAccessible(true);
                if (m.getName() === 'onReadCompleted') {
                    console.log("[*] Found onReadCompleted: " + m.toString());
                }
            }

            // Hook the private onReadCompleted - 5 args
            var origOnReadCompleted = CronetBidirectionalStream.onReadCompleted.overload('java.nio.ByteBuffer', 'int', 'int', 'int', 'long');
            origOnReadCompleted.implementation = function(byteBuffer, bytesRead, initialPosition, initialLimit, receivedByteCount) {
                if (bytesRead > 0) {
                    try {
                        var bytes = Java.array('byte', new Array(bytesRead));
                        byteBuffer.position(initialPosition);
                        byteBuffer.get(bytes, 0, bytesRead);
                        byteBuffer.position(initialPosition);
                        var Str = Java.use('java.lang.String');
                        var s = Str.$new(bytes, 0, bytesRead, 'UTF-8');
                        console.log('[onReadCompleted|' + bytesRead + 'b] ' + s.substring(0, 8192));
                    } catch(e) {
                        try {
                            byteBuffer.position(initialPosition);
                            var rbs = Java.array('byte', new Array(Math.min(bytesRead, 64)));
                            byteBuffer.get(rbs, 0, Math.min(bytesRead, 64));
                            byteBuffer.position(initialPosition);
                            var hex = '';
                            for (var k = 0; k < rbs.length; k++) {
                                hex += ('0' + (rbs[k] & 0xFF).toString(16)).slice(-2);
                            }
                            console.log('[onReadCompleted|' + bytesRead + 'b|BIN] ' + hex);
                        } catch(e2) {
                            console.log('[onReadCompleted|' + bytesRead + 'b] (binary, could not decode)');
                        }
                    }
                }
                return origOnReadCompleted.call(this, byteBuffer, bytesRead, initialPosition, initialLimit, receivedByteCount);
            };
            console.log("[*] Hooked CronetBidirectionalStream.onReadCompleted");
        } catch(e) {
            console.log("[!] onReadCompleted hook: " + e);
        }

        // HOOK 2: Also hook onStreamReady to log when streaming starts
        try {
            var CBS2 = Java.use('com.ttnet.org.chromium.net.impl.CronetBidirectionalStream');
            var origOnStreamReady = CBS2.onStreamReady.overload('boolean');
            origOnStreamReady.implementation = function(isReady) {
                console.log('[onStreamReady] ready=' + isReady);
                return origOnStreamReady.call(this, isReady);
            };
            console.log("[*] Hooked CronetBidirectionalStream.onStreamReady");
        } catch(e) {
            console.log("[!] onStreamReady: " + e);
        }

        // HOOK 3: UrlRequest.read(ByteBuffer) - backup
        try {
            var UrlRequest = Java.use('com.ttnet.org.chromium.net.UrlRequest');
            var origRead = UrlRequest.read;
            origRead.implementation = function(byteBuffer) {
                origRead.call(this, byteBuffer);
                var remaining = byteBuffer.limit() - byteBuffer.position();
                if (remaining > 10) {
                    try {
                        var bytes = Java.array('byte', new Array(remaining));
                        var pos = byteBuffer.position();
                        byteBuffer.position(0);
                        byteBuffer.get(bytes, 0, remaining);
                        byteBuffer.position(pos);
                        var String = Java.use('java.lang.String');
                        var s = String.$new(bytes, 0, remaining, 'UTF-8');
                        if (s.indexOf('{') >= 0 || s.indexOf('data:') >= 0 || s.indexOf('event:') >= 0) {
                            console.log('[UrlRequest.read|' + remaining + 'b] ' + s.substring(0, 4096));
                        }
                    } catch(e) {}
                }
            };
            console.log("[*] Hooked UrlRequest.read(ByteBuffer)");
        } catch(e) {}

        // HOOK 4: onError to see if connections are failing
        try {
            var CBS4 = Java.use('com.ttnet.org.chromium.net.impl.CronetBidirectionalStream');
            var origOnError = CBS4.onError.overload('int', 'int', 'int', 'java.lang.String', 'long');
            origOnError.implementation = function(netError, quicError, sslError, errorString, receivedByteCount) {
                console.log('[onError] net=' + netError + ' quic=' + quicError + ' ssl=' + sslError + ' msg=' + errorString);
                return origOnError.call(this, netError, quicError, sslError, errorString, receivedByteCount);
            };
            console.log("[*] Hooked onError");
        } catch(e) {
            console.log("[!] onError: " + e);
        }

        console.log("[*] Cronet Java hook v6 - Ready! Chat SSE data will appear above ^");
    });
}, 1500);
