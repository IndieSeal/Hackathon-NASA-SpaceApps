let wsOn = false, pollOk = false;
const uniqueUsers = new Map();

async function history(initial){
    try {
        const r = await fetch(API + "/history"); if (!r.ok) throw 0;
        const list = await r.json();
        pollOk = true;
        if (initial){
            // For each user
            list.slice(-MAX).forEach(d => {
                if(!uniqueUsers.has(d.astronaut_id)){
                    console.log("NEW REGISTERED: ");
                    console.log(d.nombrec);
                    uniqueUsers.set(d.astronaut_id, true);
                }
            });
            
            if (list.length){
            }
        }
    }
    catch(e){
        pollOk = false;
    }
}

history(true);
setInterval(() => { if (!wsOn) history(false); }, 2000);