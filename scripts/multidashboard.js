let wsOn = false, pollOk = false;
const uniqueUsers = new Map();

async function history(initial){
    try {
        const r = await fetch(API + "/history"); if (!r.ok) throw 0;
        const list = await r.json();
        pollOk = true;
        if (initial){
            // For each user I want to make a small panel where it shows ONE of the important data, have some arrows (to the left and right) to flip through the different data types (temp, oxygen, etc). Then below that data which should be a graph or a number, below should be a small panel that is like Green, Yellow or Red that quickly shows their condition.
            // And finally, to the left of those two together, just a photo of the astronaut and their name. Thats what this script should become later on.
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