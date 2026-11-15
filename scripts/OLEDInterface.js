export default class OLEDInterface {
    port;
    writer;

    constructor(){}

    async connect() {
        port = await navigator.serial.requestPort();
        await port.open({
            baudRate: 9600
        });
        writer = port.writable.getWriter();
    }

    disconnect(){

    }

    async write(data, payload){
        /*
            0 - Frecuencia Cardiaca: int (4 Bytes)
            1 - Variabilidad: float (%.1f)
            2 - Saturación: float (%.1f)
            3 - Presión Arterial: (string + \0 (null terminator)) 
            4 - Temperatura: float (%.1f)
            5 - Frecuencia Respitaroria: int
            6 - Indice de Choque: float (%.2f)
            7 - Presión de Pulso: int
        */


        /*
            DATA (1 byte) - Payload (Variable) - EOP (0xFF)
        */
       const encoder = new TextEncoder();
       await this.writer(new Int8Array([data]));
        switch(data){
            case 0:
            case 5:
            case 7:
                await this.writer(new Int32Array([payload]));
                break;
            case 1:
            case 2:
            case 4:
            case 6:
                await this.writer(new Float32Array([payload]));
                break;
            case 3:
                await this.writer(encoder.encode(payload));
                await this.writer(new Int8Array([0]));
                break;
        }
        await this.writer(new Int8Array([0xFF]));
    }


}