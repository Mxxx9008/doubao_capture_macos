// Hook SSL stacks - v6: capture SSL_write in onEnter, SSL_read in onLeave
var hookedLibs = {};

function hookSSFLibByName(name) {
    if (hookedLibs[name]) return;
    try {
        var mod = Process.findModuleByName(name);
        if (!mod) return;
        hookedLibs[name] = true;
        console.log("[*] Hooking " + name + " at " + mod.base);

        var symbols = mod.enumerateExports();
        var count = 0;
        for (var j = 0; j < symbols.length; j++) {
            var sym = symbols[j];
            if (sym.name === 'SSL_read') {
                var libName = name;
                Interceptor.attach(sym.address, {
                    onEnter: function(args) {
                        this.buf = args[1];
                        this.count = args[2].toInt32();
                        this.lib = libName;
                    },
                    onLeave: function(retval) {
                        var bytes = retval.toInt32();
                        if (bytes > 0 && bytes < 65536) {
                            try {
                                var display = this.buf.readUtf8String(Math.min(bytes, 4096));
                                console.log('[SSL_read|' + this.lib + '|' + bytes + 'b] ' + display.substring(0, 4096));
                            } catch(e) {
                                try {
                                    var raw = this.buf.readByteArray(Math.min(bytes, 64));
                                    var hex = '';
                                    for (var k = 0; k < raw.byteLength; k++) {
                                        hex += ('0' + (raw[k] & 0xFF).toString(16)).slice(-2);
                                    }
                                    console.log('[SSL_read|' + this.lib + '|' + bytes + 'b|BIN] ' + hex);
                                } catch(e2) {
                                    console.log('[SSL_read|' + this.lib + '|' + bytes + 'b|ERR] ' + e2);
                                }
                            }
                        }
                    }
                });
                count++;
            } else if (sym.name === 'SSL_write') {
                var libName = name;
                Interceptor.attach(sym.address, {
                    onEnter: function(args) {
                        this.buf = args[1];
                        this.bytes = args[2].toInt32();
                        this.lib = libName;
                        // Capture in onEnter - buffer still valid
                        if (this.bytes > 0 && this.bytes < 65536) {
                            try {
                                var display = this.buf.readUtf8String(Math.min(this.bytes, 4096));
                                console.log('[SSL_write|' + this.lib + '|' + this.bytes + 'b] ' + display.substring(0, 4096));
                            } catch(e) {
                                try {
                                    var raw = this.buf.readByteArray(Math.min(this.bytes, 64));
                                    var hex = '';
                                    for (var k = 0; k < raw.byteLength; k++) {
                                        hex += ('0' + (raw[k] & 0xFF).toString(16)).slice(-2);
                                    }
                                    console.log('[SSL_write|' + this.lib + '|' + this.bytes + 'b|BIN] ' + hex);
                                } catch(e2) {
                                    console.log('[SSL_write|' + this.lib + '|' + this.bytes + 'b|ERR] ' + e2);
                                }
                            }
                        }
                    }
                });
                count++;
            }
        }
        console.log("[*] " + name + ": hooked " + count + " SSL functions");
    } catch(e) {
        console.log("[!] " + name + ": " + e);
    }
}

function discoverAndHook() {
    var targets = ['libssl.so', 'libttboringssl.so', 'libsscronet.so', 'libboringssl.so', 'libcronet.so'];
    for (var i = 0; i < targets.length; i++) {
        hookSSFLibByName(targets[i]);
    }
}

setTimeout(function() {
    console.log("[*] Native SSL hook v6 - onEnter for write, onLeave for read");
    discoverAndHook();

    var dlopen = Module.findExportByName(null, 'android_dlopen_ext') || Module.findExportByName(null, 'dlopen');
    if (dlopen) {
        Interceptor.attach(dlopen, {
            onEnter: function(args) { this.path = args[0].readUtf8String(); },
            onLeave: function(retval) {
                var p = this.path || '';
                if (p.indexOf('libssl') >= 0 || p.indexOf('libttboringssl') >= 0 ||
                    p.indexOf('libsscronet') >= 0 || p.indexOf('libboringssl') >= 0) {
                    console.log("[*] SSL lib loaded: " + p);
                    setTimeout(function(path) {
                        hookSSFLibByName(path.split('/').pop());
                    }, 200, p);
                }
            }
        });
    }
    console.log("[*] Native SSL hook v6 - Ready!");
}, 500);
