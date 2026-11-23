import assert from 'node:assert/strict';
import { updateWorkspace } from './workspace_state.mjs';
const signedIn={user:{id:'team1'},changes:[]};
assert.equal(updateWorkspace(signedIn,null),null);
assert.equal(updateWorkspace(null,()=>assert.fail('Stale redraw ran after sign-out')),null);
assert.equal(updateWorkspace(null,signedIn),signedIn);
assert.deepEqual(updateWorkspace(signedIn,s=>({...s,changes:[{id:'change'}]})).changes,[{id:'change'}]);
console.log('Session expiry preserves the signed-out state during delayed UI updates');
