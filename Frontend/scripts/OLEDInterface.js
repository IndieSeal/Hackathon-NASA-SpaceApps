export default class OLEDInterface {
    port;
    writer;

    constructor(){}

    queue = Promise.resolve();
    delay = 1000;
    timer = null;
    busy = false;
    onError = null;

    async connect() {
        this.port = await navigator.serial.requestPort();
        await this.port.open({
            baudRate: 9600
        });
        
        this.writer = this.port.writable.getWriter();
    }

    async disconnect() {
        this.stop();
    
        await this.queue.catch(() => {});
        this.writer?.releaseLock();
        await this.port?.close();
        this.writer = this.port = null;
    }

    async write(data, payload) {
        let body;
        switch (data) {
            case 0:
            case 5:
            case 7:
                body = new Uint8Array(new Int32Array([Math.round(payload)]).buffer); break;
            case 1:
            case 2:
            case 4:
            case 6:
                body = new Uint8Array(new Float32Array([payload]).buffer); break;
            case 3:
                body = new Uint8Array([...new TextEncoder().encode(payload), 0]); break;
            default:
                throw new Error("Tipo de dato desconocido: " + data);
        }
        const frame = new Uint8Array(body.length + 2);   // DATA + payload + 0xFF
        frame[0] = data;
        frame.set(body, 1);
        frame[frame.length - 1] = 0xFF;
        this.queue = this.queue.catch(() => {}).then(() => this.writer.write(frame));
        return this.queue;
    }

    start(getUpdates, delay = this.delay) {
        this.stop();
        this.delay = delay;
        this.timer = setInterval(async () => {
            if (this.busy || !this.writer) return;
            this.busy = true;
            try {
                for (const [code, value] of getUpdates()) await this.write(code, value);
            } catch (e) {
                if (this.timer) this.onError?.(e);
            } finally {
                this.busy = false;
            }
        }, delay);
    }

    stop() {
        clearInterval(this.timer);
        this.timer = null;
    }
}